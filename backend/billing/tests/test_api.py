import io
from datetime import timedelta

import pytest
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from billing import hub3, services
from billing.models import Client, Document
from billing.pdf import payment_payload

from .conftest import item, make_draft, tomorrow

pytestmark = pytest.mark.django_db

Kind = Document.Kind


def body(client, /, **changes):
    return {
        "kind": "invoice",
        "client": client.pk,
        "due_date": tomorrow().isoformat(),
        "items": [{"description": "Izrada web stranice", "quantity": "1", "unit_price": "900.00"}],
        **changes,
    }


# --- pristup -----------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["/api/company/", "/api/summary/", "/api/clients/", "/api/documents/", "/api/documents/1/pdf/"],
)
def test_everything_is_closed_without_owner_login(url, django_user_model):
    anonymous = APIClient()
    assert anonymous.get(url).status_code == 403

    django_user_model.objects.create_user("gost", password="tajna-lozinka")
    anonymous.login(username="gost", password="tajna-lozinka")
    assert anonymous.get(url).status_code == 403


def test_login_flow_with_csrf(django_user_model):
    django_user_model.objects.create_user("vlasnik", password="tajna-lozinka", is_staff=True)
    client = APIClient(enforce_csrf_checks=True)
    data = {"username": "vlasnik", "password": "tajna-lozinka"}
    assert client.post("/api/auth/login/", data, format="json").status_code == 403

    assert client.get("/api/auth/me/").json() == {"authenticated": False, "username": ""}
    token = client.cookies["csrftoken"].value

    def post(url, payload=None, origin="https://racuni.test"):
        return client.post(url, payload, format="json", HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN=origin)

    assert post("/api/auth/login/", data, origin="https://zla-stranica.test").status_code == 403
    assert post("/api/auth/login/", {**data, "password": "kriva"}).status_code == 400
    assert post("/api/auth/login/", data).status_code == 200
    assert client.get("/api/auth/me/").json() == {"authenticated": True, "username": "vlasnik"}

    token = client.cookies["csrftoken"].value  # Django ga mijenja pri prijavi
    assert post("/api/auth/logout/").status_code == 200
    assert client.get("/api/documents/").status_code == 403


# --- izdavatelj --------------------------------------------------------------


def test_company_settings(api):
    assert api.get("/api/company/").json()["missing_for_issuing"] == [
        "naziv",
        "adresa",
        "mjesto",
        "OIB",
        "IBAN",
    ]
    data = {
        "name": "Primjer, obrt",
        "address": "Radnička cesta 1",
        "city": "47000 Karlovac",
        "oib": "12345678903",
        "iban": "hr37 9999 9990 0000 0000 1",
        "due_days": 10,
    }
    response = api.put("/api/company/", data, format="json")
    assert response.status_code == 200, response.content
    assert response.json()["iban"] == "HR3799999990000000001"
    assert response.json()["missing_for_issuing"] == []

    bad = api.put("/api/company/", {**data, "oib": "12345678900", "iban": "HR00"}, format="json")
    assert bad.status_code == 400
    assert set(bad.json()) == {"oib", "iban"}


# --- klijenti ----------------------------------------------------------------


def test_client_crud_and_archive(api, company):
    created = api.post("/api/clients/", {"name": "Ana Anić", "oib": "11111111119"}, format="json")
    assert created.status_code == 201
    pk = created.json()["id"]

    assert api.post("/api/clients/", {"name": "X", "oib": "123"}, format="json").status_code == 400

    api.put(f"/api/clients/{pk}/", {"name": "Ana Anić", "archived": True}, format="json")
    assert api.get("/api/clients/").json() == []
    assert len(api.get("/api/clients/?archived=1").json()) == 1

    assert api.delete(f"/api/clients/{pk}/").status_code == 204


def test_client_with_documents_cannot_be_deleted(api, company, client_a):
    make_draft(client_a)
    response = api.delete(f"/api/clients/{client_a.pk}/")
    assert response.status_code == 409
    assert "arhivirati" in response.json()["detail"]
    assert Client.objects.filter(pk=client_a.pk).exists()


# --- dokumenti ---------------------------------------------------------------


def test_create_edit_issue_pay(api, company, client_a):
    created = api.post("/api/documents/", body(client_a), format="json")
    assert created.status_code == 201, created.content
    document = created.json()
    assert (document["status"], document["number"], document["total"]) == ("draft", "", "900.00")
    assert document["items"][0]["amount"] == "900.00"
    url = f"/api/documents/{document['id']}/"

    items = [
        {"description": "Izrada web stranice", "quantity": "1", "unit_price": "900"},
        {
            "description": "Održavanje",
            "unit": "mj",
            "quantity": "12",
            "unit_price": "25",
            "discount_percent": "10",
        },
    ]
    edited = api.put(url, body(client_a, items=items), format="json")
    assert edited.status_code == 200, edited.content
    assert edited.json()["total"] == "1170.00"

    issued = api.post(f"{url}issue/").json()
    assert (issued["status"], issued["number"]) == ("issued", "1/1/1")
    assert issued["issue_date"] == timezone.localdate().isoformat()
    assert issued["buyer_name"] == "Pekara Klas d.o.o."

    assert api.put(url, body(client_a), format="json").status_code == 409
    assert api.delete(url).status_code == 409
    assert api.post(f"{url}issue/").status_code == 409

    assert api.post(f"{url}mark-paid/").json()["status"] == "paid"
    assert api.post(f"{url}cancel/").json()["status"] == "cancelled"


def test_draft_can_be_deleted(api, company, client_a):
    pk = api.post("/api/documents/", body(client_a), format="json").json()["id"]
    assert api.delete(f"/api/documents/{pk}/").status_code == 204
    assert not Document.objects.exists()


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"client": 999}, "client"),
        ({"due_date": "sutra"}, "due_date"),
        ({"kind": "storno"}, "kind"),
        ({"items": [{"description": "", "quantity": "1", "unit_price": "1"}]}, "items"),
        ({"items": [{"description": "A", "quantity": "0", "unit_price": "1"}]}, "items"),
        ({"items": [{"description": "A", "quantity": "1", "unit_price": "-1"}]}, "items"),
        (
            {
                "items": [
                    {
                        "description": "A",
                        "quantity": "1",
                        "unit_price": "1",
                        "discount_percent": "101",
                    }
                ]
            },
            "items",
        ),
        (
            {"items": [{"description": "A", "quantity": "1", "unit_price": "1", "vat_rate": "20"}]},
            "items",
        ),
    ],
)
def test_bad_input_is_rejected(api, company, client_a, changes, field):
    response = api.post("/api/documents/", body(client_a, **changes), format="json")
    assert response.status_code == 400
    assert field in response.json()
    assert not Document.objects.exists()


def test_kind_cannot_change_after_creation(api, company, client_a):
    pk = api.post("/api/documents/", body(client_a), format="json").json()["id"]
    response = api.put(f"/api/documents/{pk}/", body(client_a, kind="quote"), format="json")
    assert response.status_code == 400


def test_vat_rates_round_trip(api, vat_company, client_a):
    items = [{"description": "A", "quantity": "1", "unit_price": "100", "vat_rate": "25"}]
    document = api.post("/api/documents/", body(client_a, items=items), format="json").json()
    assert (document["net_total"], document["vat_total"], document["total"]) == (
        "100.00",
        "25.00",
        "125.00",
    )
    assert document["vat_breakdown"] == [{"rate": "25.00", "base": "100.00", "vat": "25.00"}]
    # Ono što API vrati mora se moći poslati natrag bez izmjene.
    again = api.put(
        f"/api/documents/{document['id']}/", body(client_a, items=document["items"]), format="json"
    )
    assert again.status_code == 200, again.content


def test_quote_to_invoice(api, company, client_a):
    quote = api.post("/api/documents/", body(client_a, kind="quote"), format="json").json()
    url = f"/api/documents/{quote['id']}/"
    assert api.post(f"{url}to-invoice/").status_code == 409  # nacrt
    assert api.post(f"{url}issue/").json()["number"] == f"P-1/{timezone.localdate().year}"
    assert api.post(f"{url}accept/").json()["status"] == "accepted"

    invoice = api.post(f"{url}to-invoice/").json()
    assert (invoice["kind"], invoice["status"], invoice["source"]) == (
        "invoice",
        "draft",
        quote["id"],
    )
    assert invoice["total"] == "900.00"


def test_list_filters_and_summary(api, company, client_a):
    paid = services.mark_paid(services.issue(make_draft(client_a, items=[item(unit_price="50")])))
    overdue = services.issue(make_draft(client_a, items=[item(unit_price="200")]))
    Document.objects.filter(pk=overdue.pk).update(due_date=timezone.localdate() - timedelta(days=3))
    services.issue(make_draft(client_a, items=[item(unit_price="300")]))
    make_draft(client_a)
    services.issue(make_draft(client_a, kind=Kind.QUOTE))

    def numbers(query):
        return sorted(row["number"] for row in api.get(f"/api/documents/?{query}").json())

    assert len(api.get("/api/documents/").json()) == 5
    assert numbers("kind=invoice&status=issued") == ["2/1/1", "3/1/1"]
    assert numbers("status=paid") == [paid.number]
    assert numbers("overdue=1") == ["2/1/1"]
    assert numbers("search=3/1") == ["3/1/1"]
    assert len(api.get("/api/documents/?search=pekara").json()) == 5

    assert api.get("/api/summary/").json() == {
        "unpaid_total": "500.00",
        "unpaid_count": 2,
        "overdue_total": "200.00",
        "overdue_count": 1,
        "invoiced_this_year": "550.00",
        "open_quotes": 1,
    }


# --- PDF ---------------------------------------------------------------------


def pdf_text(response) -> str:
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    reader = PdfReader(io.BytesIO(response.content))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_invoice_pdf_has_croatian_letters_totals_and_payment_details(api, company, client_a):
    company.footer_note = "Obveznik nije u sustavu PDV-a."
    company.save()
    invoice = services.issue(
        make_draft(client_a, items=[item("Čišćenje i održavanje računala", "2.5", "30", unit="h")])
    )
    response = api.get(f"/api/documents/{invoice.pk}/pdf/")
    text = pdf_text(response)
    assert 'filename="racun-1-1-1.pdf"' in response["Content-Disposition"]
    for expected in [
        "RAČUN br. 1/1/1",
        "Pekara Klas d.o.o.",
        "OIB: 11111111119",
        "Čišćenje i održavanje računala",
        "2,5",
        "75,00 EUR",
        "Obveznik nije u sustavu PDV-a.",
        "IBAN: HR3799999990000000001",
        "HR00 1-1-1",
    ]:
        assert expected in text, expected
    assert "PDV 25" not in text


def test_vat_invoice_pdf_shows_the_vat_breakdown(api, vat_company, client_a):
    invoice = services.issue(
        make_draft(client_a, items=[item(unit_price="1234.50", vat_rate="25")])
    )
    text = pdf_text(api.get(f"/api/documents/{invoice.pk}/pdf/"))
    for expected in [
        "Osnovica",
        "1.234,50 EUR",
        "PDV 25 % na 1.234,50",
        "308,63 EUR",
        "1.543,13 EUR",
    ]:
        assert expected in text, expected


def test_draft_and_quote_pdfs_have_no_payment_block(api, company, client_a):
    draft = pdf_text(api.get(f"/api/documents/{make_draft(client_a).pk}/pdf/"))
    assert "RAČUN – NACRT" in draft
    assert "PODACI ZA PLAĆANJE" not in draft

    quote = services.issue(make_draft(client_a, kind=Kind.QUOTE))
    text = pdf_text(api.get(f"/api/documents/{quote.pk}/pdf/"))
    assert f"PONUDA br. P-1/{timezone.localdate().year}" in text
    assert "Ponuda vrijedi do" in text
    assert "PODACI ZA PLAĆANJE" not in text


def test_payment_barcode_payload_follows_the_hub3_layout(company, client_a):
    invoice = services.issue(make_draft(client_a, items=[item(unit_price="123.55")]))
    assert payment_payload(invoice, company).split("\n") == [
        "HRVHUB30",
        "EUR",
        "000000000012355",
        "Pekara Klas d.o.o.",
        "Ulica žita 5",
        "47000 Karlovac",
        "Primjer, obrt",
        "Radnička cesta 1",
        "47000 Karlovac",
        "HR3799999990000000001",
        "HR00",
        "1-1-1",
        "",
        "Račun 1/1/1",
        "",
    ]


def test_barcode_text_is_cleaned_and_truncated():
    text = hub3.payload(
        amount=1,
        payer_name="Tvrtka & sinovi „Klas” – proizvodnja, trgovina i usluge d.o.o.",
        payer_address="",
        payer_city="",
        recipient_name="x" * 40,
        recipient_address="",
        recipient_city="",
        iban="HR3799999990000000001",
        reference="",
        description="a\nb",
    )
    fields = text.split("\n")
    assert fields[3] == "Tvrtka sinovi Klas proizvodnja"
    assert len(fields[3]) <= 30
    assert fields[6] == "x" * 25
    assert (fields[10], fields[11]) == ("HR99", "")
    assert fields[13] == "a b"
    assert text.count("\n") == 14


def test_barcode_has_nine_data_columns_and_reads_as_binary():
    rows = hub3.modules("HRVHUB30\nEUR\n000000000012355\n")
    # početak + lijevi pokazatelj + 9 stupaca + desni pokazatelj po 17 modula, kraj 18
    assert {len(row) for row in rows} == {(9 + 3) * 17 + 18}
    assert all(row.startswith("11111111010101000") for row in rows)
