"""Poslovna pravila: spremanje nacrta, izdavanje, plaćanje, storno, ponuda → račun."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import money
from .models import Client, Company, Counter, Document, Item

Kind = Document.Kind
Status = Document.Status


class RuleError(Exception):
    """Radnja nije dopuštena; poruka je namijenjena korisniku."""


def _recalculate(document: Document, company: Company) -> None:
    result = money.totals(document.items.all(), vat_registered=company.vat_registered)
    document.net_total, document.vat_total, document.total = result.net, result.vat, result.total
    document.save(update_fields=["net_total", "vat_total", "total"])


@transaction.atomic
def save_draft(*, document: Document | None, data: dict, items: list[dict]) -> Document:
    """Stvara nacrt ili mijenja postojeći. Izdani dokument se ne može mijenjati."""
    company = Company.load()
    if document is None:
        document = Document(kind=data["kind"])
    elif not document.is_draft:
        raise RuleError("Izdani dokument se ne može mijenjati. Možete ga stornirati.")

    document.client = data["client"]
    document.due_date = data["due_date"]
    document.delivery_date = data.get("delivery_date")
    document.note = data.get("note", "")
    document.save()

    document.items.all().delete()
    Item.objects.bulk_create(
        Item(
            document=document,
            position=position,
            description=item["description"],
            unit=item.get("unit") or "kom",
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            discount_percent=item.get("discount_percent", money.ZERO),
            # Tko nije u sustavu PDV-a, ne smije iskazati PDV na dokumentu.
            vat_rate=item.get("vat_rate", money.ZERO) if company.vat_registered else money.ZERO,
        )
        for position, item in enumerate(items)
    )
    _recalculate(document, company)
    return document


def _format_number(kind: str, sequence: int, year: int, company: Company) -> str:
    if kind == Kind.INVOICE:
        return f"{sequence}/{company.premise_code}/{company.device_code}"
    return f"P-{sequence}/{year}"


@transaction.atomic
def issue(document: Document) -> Document:
    """Izdaje nacrt: dodjeljuje sljedeći broj i današnji datum.

    Datum izdavanja je uvijek današnji, pa brojevi idu istim redom kao datumi.
    Brojač se zaključava do kraja transakcije, pa dva istodobna izdavanja ne
    mogu dobiti isti broj niti ostaviti rupu u nizu.
    """
    document = Document.objects.select_for_update().get(pk=document.pk)
    if not document.is_draft:
        raise RuleError("Dokument je već izdan.")
    if not document.items.exists():
        raise RuleError("Dodajte barem jednu stavku prije izdavanja.")

    company = Company.load()
    missing = company.missing_for_issuing()
    if missing:
        raise RuleError(f"U postavkama upišite podatke izdavatelja: {', '.join(missing)}.")

    today = timezone.localdate()
    if document.due_date < today:
        what = "Rok plaćanja" if document.kind == Kind.INVOICE else "Datum do kojeg ponuda vrijedi"
        raise RuleError(f"{what} ne može biti u prošlosti.")

    Counter.objects.get_or_create(kind=document.kind, year=today.year)
    counter = Counter.objects.select_for_update().get(kind=document.kind, year=today.year)
    counter.last += 1
    counter.save(update_fields=["last"])

    client: Client = document.client
    document.year = today.year
    document.sequence = counter.last
    document.number = _format_number(document.kind, counter.last, today.year, company)
    document.issue_date = today
    document.issued_at = timezone.now()
    document.status = Status.ISSUED
    document.buyer_name = client.name
    document.buyer_address = client.address
    document.buyer_city = client.city
    document.buyer_oib = client.oib
    document.save()
    _recalculate(document, company)
    return document


def _require(document: Document, kind: str, statuses: set[str], message: str) -> None:
    if document.kind != kind or document.status not in statuses:
        raise RuleError(message)


@transaction.atomic
def mark_paid(document: Document) -> Document:
    document = Document.objects.select_for_update().get(pk=document.pk)
    _require(
        document, Kind.INVOICE, {Status.ISSUED}, "Plaćenim se može označiti samo izdani račun."
    )
    document.status = Status.PAID
    document.paid_at = timezone.now()
    document.save(update_fields=["status", "paid_at"])
    return document


@transaction.atomic
def set_quote_outcome(document: Document, *, accepted: bool) -> Document:
    document = Document.objects.select_for_update().get(pk=document.pk)
    _require(
        document, Kind.QUOTE, {Status.ISSUED}, "Odgovor se može upisati samo za izdanu ponudu."
    )
    document.status = Status.ACCEPTED if accepted else Status.REJECTED
    document.save(update_fields=["status"])
    return document


@transaction.atomic
def cancel(document: Document) -> Document:
    """Stornira izdani dokument. Broj ostaje zauzet."""
    document = Document.objects.select_for_update().get(pk=document.pk)
    if document.status == Status.DRAFT:
        raise RuleError("Nacrt se ne stornira, nego briše.")
    if document.status == Status.CANCELLED:
        raise RuleError("Dokument je već storniran.")
    document.status = Status.CANCELLED
    document.cancelled_at = timezone.now()
    document.save(update_fields=["status", "cancelled_at"])
    return document


def delete_draft(document: Document) -> None:
    if not document.is_draft:
        raise RuleError("Izdani dokument se ne može obrisati. Možete ga stornirati.")
    document.delete()


@transaction.atomic
def quote_to_invoice(quote: Document) -> Document:
    """Iz izdane ili prihvaćene ponude stvara nacrt računa s istim stavkama."""
    _require(
        quote,
        Kind.QUOTE,
        {Status.ISSUED, Status.ACCEPTED},
        "Račun se može izraditi samo iz izdane ili prihvaćene ponude.",
    )
    company = Company.load()
    invoice = Document.objects.create(
        kind=Kind.INVOICE,
        client=quote.client,
        due_date=timezone.localdate() + timedelta(days=company.due_days),
        note=quote.note,
        source=quote,
    )
    Item.objects.bulk_create(
        Item(
            document=invoice,
            position=item.position,
            description=item.description,
            unit=item.unit,
            quantity=item.quantity,
            unit_price=item.unit_price,
            discount_percent=item.discount_percent,
            vat_rate=item.vat_rate,
        )
        for item in quote.items.all()
    )
    _recalculate(invoice, company)
    return invoice
