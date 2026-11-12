import os
from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from billing import services
from billing.models import Counter, Document
from billing.services import RuleError

from .conftest import item, make_draft, tomorrow

pytestmark = pytest.mark.django_db

Kind = Document.Kind
Status = Document.Status


def test_ci_runs_on_the_database_it_claims():
    """U CI-ju posao „postgres” ne smije potiho raditi na SQLiteu."""
    expected = os.environ.get("EXPECTED_DATABASE")
    if not expected:
        pytest.skip("EXPECTED_DATABASE nije postavljen (lokalno pokretanje)")
    assert connection.vendor == expected


# --- nacrt -------------------------------------------------------------------


def test_draft_has_totals_but_no_number(company, client_a):
    draft = make_draft(client_a, items=[item(quantity="2", unit_price="50"), item(unit_price="20")])
    assert draft.status == Status.DRAFT
    assert (draft.number, draft.sequence, draft.issue_date) == ("", None, None)
    assert draft.total == D("120.00")
    assert [i.position for i in draft.items.all()] == [0, 1]


def test_saving_a_draft_replaces_its_items(company, client_a):
    draft = make_draft(client_a, items=[item(), item()])
    services.save_draft(
        document=draft,
        data={"kind": Kind.INVOICE, "client": client_a, "due_date": tomorrow()},
        items=[item(unit_price="7")],
    )
    draft.refresh_from_db()
    assert draft.items.count() == 1
    assert draft.total == D("7.00")


def test_vat_is_dropped_when_issuer_is_outside_the_vat_system(company, client_a):
    draft = make_draft(client_a, items=[item(vat_rate="25")])
    assert draft.items.get().vat_rate == D("0")
    assert (draft.vat_total, draft.total) == (D("0.00"), D("100.00"))


def test_vat_is_kept_when_issuer_is_in_the_vat_system(vat_company, client_a):
    draft = make_draft(client_a, items=[item(vat_rate="25")])
    assert (draft.net_total, draft.vat_total, draft.total) == (D("100.00"), D("25.00"), D("125.00"))


# --- izdavanje ---------------------------------------------------------------


def test_issuing_assigns_number_date_and_buyer_snapshot(company, client_a):
    invoice = services.issue(make_draft(client_a))
    assert invoice.status == Status.ISSUED
    assert invoice.number == "1/1/1"
    assert (invoice.sequence, invoice.year) == (1, timezone.localdate().year)
    assert invoice.issue_date == timezone.localdate()
    assert invoice.buyer_name == "Pekara Klas d.o.o."
    assert invoice.buyer_oib == "11111111119"


def test_numbers_are_sequential_and_separate_per_kind(company, client_a):
    invoices = [services.issue(make_draft(client_a)).number for _ in range(3)]
    quotes = [services.issue(make_draft(client_a, kind=Kind.QUOTE)).number for _ in range(2)]
    year = timezone.localdate().year
    assert invoices == ["1/1/1", "2/1/1", "3/1/1"]
    assert quotes == [f"P-1/{year}", f"P-2/{year}"]


def test_number_uses_premise_and_device_codes(company, client_a):
    company.premise_code, company.device_code = "POSL1", "2"
    company.save()
    assert services.issue(make_draft(client_a)).number == "1/POSL1/2"


def test_numbering_restarts_each_year(company, client_a, monkeypatch):
    services.issue(make_draft(client_a))
    next_year = timezone.localdate().replace(month=1, day=2, year=timezone.localdate().year + 1)
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: next_year)
    draft = make_draft(client_a, due_date=next_year + timedelta(days=5))
    invoice = services.issue(draft)
    assert (invoice.sequence, invoice.year) == (1, next_year.year)


def test_deleted_drafts_leave_no_gap_in_numbers(company, client_a):
    services.issue(make_draft(client_a))
    services.delete_draft(make_draft(client_a))
    assert services.issue(make_draft(client_a)).number == "2/1/1"


def test_failed_issue_does_not_consume_a_number(company, client_a):
    services.issue(make_draft(client_a))
    with pytest.raises(RuleError):
        services.issue(make_draft(client_a, items=[]))
    assert Counter.objects.get(kind=Kind.INVOICE).last == 1
    assert services.issue(make_draft(client_a)).number == "2/1/1"


def test_database_refuses_a_duplicate_number(company, client_a):
    first = services.issue(make_draft(client_a))
    second = make_draft(client_a)
    second.year, second.sequence = first.year, first.sequence
    with pytest.raises(IntegrityError), transaction.atomic():
        second.save()


def test_buyer_snapshot_survives_later_client_changes(company, client_a):
    invoice = services.issue(make_draft(client_a))
    client_a.name = "Novo ime d.o.o."
    client_a.save()
    invoice.refresh_from_db()
    assert invoice.buyer_name == "Pekara Klas d.o.o."


@pytest.mark.parametrize(
    ("prepare", "message"),
    [
        (lambda c, cl: make_draft(cl, items=[]), "barem jednu stavku"),
        (
            lambda c, cl: make_draft(cl, due_date=timezone.localdate() - timedelta(days=1)),
            "prošlosti",
        ),
        (lambda c, cl: services.issue(make_draft(cl)), "već izdan"),
    ],
)
def test_issue_is_refused(company, client_a, prepare, message):
    document = prepare(company, client_a)
    with pytest.raises(RuleError, match=message):
        services.issue(document)


def test_issue_needs_issuer_details(company, client_a):
    company.oib = company.iban = ""
    company.save()
    with pytest.raises(RuleError, match="OIB, IBAN"):
        services.issue(make_draft(client_a))


# --- izdani dokument ---------------------------------------------------------


def test_issued_document_cannot_be_changed_or_deleted(company, client_a):
    invoice = services.issue(make_draft(client_a))
    with pytest.raises(RuleError, match="ne može mijenjati"):
        services.save_draft(
            document=invoice,
            data={"kind": Kind.INVOICE, "client": client_a, "due_date": tomorrow()},
            items=[item(unit_price="1")],
        )
    with pytest.raises(RuleError, match="ne može obrisati"):
        services.delete_draft(invoice)
    invoice.refresh_from_db()
    assert invoice.total == D("100.00")


def test_invoice_lifecycle_issue_pay_cancel(company, client_a):
    invoice = services.issue(make_draft(client_a))
    paid = services.mark_paid(invoice)
    assert paid.status == Status.PAID and paid.paid_at is not None
    with pytest.raises(RuleError, match="samo izdani račun"):
        services.mark_paid(paid)
    cancelled = services.cancel(paid)
    assert cancelled.status == Status.CANCELLED
    assert cancelled.number == "1/1/1"  # broj ostaje zauzet
    with pytest.raises(RuleError, match="već storniran"):
        services.cancel(cancelled)
    assert services.issue(make_draft(client_a)).number == "2/1/1"


def test_draft_is_deleted_not_cancelled(company, client_a):
    with pytest.raises(RuleError, match="briše"):
        services.cancel(make_draft(client_a))


# --- ponude ------------------------------------------------------------------


def test_quote_outcome(company, client_a):
    quote = services.issue(make_draft(client_a, kind=Kind.QUOTE))
    assert services.set_quote_outcome(quote, accepted=True).status == Status.ACCEPTED
    with pytest.raises(RuleError, match="samo za izdanu ponudu"):
        services.set_quote_outcome(quote, accepted=False)
    with pytest.raises(RuleError, match="samo izdani račun"):
        services.mark_paid(quote)


def test_quote_becomes_a_draft_invoice_with_the_same_items(company, client_a):
    quote = services.issue(
        make_draft(
            client_a,
            kind=Kind.QUOTE,
            items=[
                item("Web", unit_price="900"),
                item("Održavanje", "12", "25", discount_percent="10"),
            ],
            note="Rok izrade 30 dana.",
        )
    )
    invoice = services.quote_to_invoice(quote)
    assert (invoice.kind, invoice.status, invoice.source) == (Kind.INVOICE, Status.DRAFT, quote)
    assert invoice.total == quote.total == D("1170.00")
    assert invoice.note == "Rok izrade 30 dana."
    assert [i.description for i in invoice.items.all()] == ["Web", "Održavanje"]
    assert invoice.due_date == timezone.localdate() + timedelta(days=company.due_days)


def test_only_issued_or_accepted_quotes_become_invoices(company, client_a):
    draft = make_draft(client_a, kind=Kind.QUOTE)
    with pytest.raises(RuleError, match="izdane ili prihvaćene ponude"):
        services.quote_to_invoice(draft)
    rejected = services.set_quote_outcome(services.issue(draft), accepted=False)
    with pytest.raises(RuleError):
        services.quote_to_invoice(rejected)
    with pytest.raises(RuleError):
        services.quote_to_invoice(services.issue(make_draft(client_a)))
