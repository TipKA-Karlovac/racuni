"""PDF ponude ili računa (A4), s barkodom za plaćanje na izdanom računu."""

from __future__ import annotations

import io
import re
from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import hub3, money
from .models import Company, Document

# Vera dolazi uz ReportLab i ima sva hrvatska slova; ugrađeni Helvetica nema č, ć i đ.
FONT, FONT_BOLD = "Vera", "VeraBd"
MODULE = 0.254 * mm  # širina najuže crte barkoda prema uputi HUB-a

_THOUSANDS = re.compile(r"(?<=\d)(?=(\d{3})+$)")

_registered = False


def _register_fonts() -> None:
    global _registered
    if not _registered:
        pdfmetrics.registerFont(TTFont(FONT, "Vera.ttf"))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, "VeraBd.ttf"))
        _registered = True


BASE = ParagraphStyle("base", fontName=FONT, fontSize=9, leading=12.5)
BOLD = ParagraphStyle("bold", parent=BASE, fontName=FONT_BOLD)
RIGHT = ParagraphStyle("right", parent=BASE, alignment=TA_RIGHT)
RIGHT_BOLD = ParagraphStyle("right-bold", parent=RIGHT, fontName=FONT_BOLD)
SMALL = ParagraphStyle("small", parent=BASE, fontSize=7.5, leading=10, textColor=colors.grey)
SMALL_RIGHT = ParagraphStyle("small-right", parent=SMALL, alignment=TA_RIGHT)
TITLE = ParagraphStyle("title", parent=BASE, fontName=FONT_BOLD, fontSize=15, leading=20)


def fmt_money(value: Decimal) -> str:
    """1234567.5 → "1.234.567,50"."""
    whole, cents = f"{money.to_cents(value):.2f}".split(".")
    sign, whole = ("-", whole[1:]) if whole.startswith("-") else ("", whole)
    grouped = _THOUSANDS.sub(".", whole)
    return f"{sign}{grouped},{cents}"


def fmt_quantity(value: Decimal) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def fmt_date(value) -> str:
    return value.strftime("%d.%m.%Y.") if value else "–"


def _p(text: str, style: ParagraphStyle = BASE) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


class Barcode(Flowable):
    """Crta PDF417 barkod iz redaka modula, u stvarnoj veličini za ispis."""

    QUIET = 2  # zona tišine u modulima
    RATIO = 3  # visina retka : širina modula

    def __init__(self, rows: list[str]):
        super().__init__()
        self.rows = rows
        self.width = (len(rows[0]) + 2 * self.QUIET) * MODULE
        self.height = (len(rows) * self.RATIO + 2 * self.QUIET) * MODULE

    def draw(self):
        canvas = self.canv
        canvas.setFillColor(colors.black)
        row_height = self.RATIO * MODULE
        for index, row in enumerate(self.rows):
            y = self.height - self.QUIET * MODULE - (index + 1) * row_height
            for match in re.finditer("1+", row):
                canvas.rect(
                    (self.QUIET + match.start()) * MODULE,
                    y,
                    (match.end() - match.start()) * MODULE,
                    row_height,
                    stroke=0,
                    fill=1,
                )


def payment_payload(document: Document, company: Company) -> str:
    """Zapis barkoda za plaćanje računa. Poziv na broj je broj računa, npr. 12-1-1."""
    return hub3.payload(
        amount=document.total,
        payer_name=document.buyer_name,
        payer_address=document.buyer_address,
        payer_city=document.buyer_city,
        recipient_name=company.name,
        recipient_address=company.address,
        recipient_city=company.city,
        iban=company.iban,
        reference=document.number.replace("/", "-"),
        description=f"Račun {document.number}",
    )


def render(document: Document) -> bytes:
    _register_fonts()
    company = Company.load()
    is_invoice = document.kind == Document.Kind.INVOICE
    draft = document.is_draft
    client = document.client
    buyer = (
        (client.name, client.address, client.city, client.oib)
        if draft
        else (document.buyer_name, document.buyer_address, document.buyer_city, document.buyer_oib)
    )

    story = []

    # --- izdavatelj i kupac ---
    seller_lines = [company.name, company.owner and f"vl. {company.owner}", company.address]
    seller_lines += [company.city, company.oib and f"OIB: {company.oib}"]
    seller_lines += [company.iban and f"IBAN: {company.iban}", company.email, company.phone]
    buyer_lines = [buyer[0], buyer[1], buyer[2], buyer[3] and f"OIB: {buyer[3]}"]
    story.append(
        Table(
            [
                [_p("IZDAVATELJ", SMALL), _p("KUPAC", SMALL)],
                [
                    _p("\n".join(line for line in seller_lines if line)),
                    _p("\n".join(line for line in buyer_lines if line), BOLD),
                ],
            ],
            colWidths=[95 * mm, 75 * mm],
            style=TableStyle(
                [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]
            ),
        )
    )
    story.append(Spacer(1, 10 * mm))

    # --- naslov i datumi ---
    name = "RAČUN" if is_invoice else "PONUDA"
    story.append(_p(f"{name} – NACRT" if draft else f"{name} br. {document.number}", TITLE))
    story.append(Spacer(1, 3 * mm))
    dates = [("Datum izdavanja", fmt_date(document.issue_date))]
    if is_invoice:
        dates.append(("Datum isporuke", fmt_date(document.delivery_date or document.issue_date)))
        dates.append(("Rok plaćanja", fmt_date(document.due_date)))
    else:
        dates.append(("Ponuda vrijedi do", fmt_date(document.due_date)))
    if document.status == Document.Status.CANCELLED:
        dates.append(("Status", "STORNIRANO"))
    story.append(
        Table(
            [[_p(label, SMALL), _p(value)] for label, value in dates],
            colWidths=[35 * mm, 60 * mm],
            hAlign="LEFT",
            style=TableStyle(
                [("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]
            ),
        )
    )
    story.append(Spacer(1, 6 * mm))

    # --- stavke ---
    vat = company.vat_registered
    header = ["R.b.", "Opis", "Količina", "Jed.", "Cijena", "Popust"]
    # Zbroj širina je 170 mm: A4 bez margina od 20 mm.
    widths = [10, 56 if vat else 68, 18, 12, 22, 16]
    if vat:
        header.append("PDV")
        widths.append(12)
    header.append("Iznos")
    widths.append(24)

    # Zaglavlja brojčanih stupaca poravnata su desno, kao i brojevi ispod njih.
    left_aligned = {"R.b.", "Opis", "Jed."}
    rows = [[_p(text, SMALL if text in left_aligned else SMALL_RIGHT) for text in header]]
    for index, item in enumerate(document.items.all(), start=1):
        row = [
            _p(f"{index}."),
            _p(item.description),
            _p(fmt_quantity(item.quantity), RIGHT),
            _p(item.unit),
            _p(fmt_money(item.unit_price), RIGHT),
            _p(f"{fmt_quantity(item.discount_percent)} %" if item.discount_percent else "", RIGHT),
        ]
        if vat:
            row.append(_p(f"{fmt_quantity(item.vat_rate)} %", RIGHT))
        row.append(
            _p(
                fmt_money(money.line_net(item.quantity, item.unit_price, item.discount_percent)),
                RIGHT,
            )
        )
        rows.append(row)
    story.append(
        Table(
            rows,
            colWidths=[width * mm for width in widths],
            repeatRows=1,
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.lightgrey),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ]
            ),
        )
    )
    story.append(Spacer(1, 4 * mm))

    # --- zbroj ---
    result = money.totals(document.items.all(), vat_registered=vat)
    summary = []
    if vat:
        summary.append((_p("Osnovica", RIGHT), _p(f"{fmt_money(result.net)} EUR", RIGHT)))
        for line in result.by_rate:
            label = f"PDV {fmt_quantity(line.rate)} % na {fmt_money(line.base)}"
            summary.append((_p(label, RIGHT), _p(f"{fmt_money(line.vat)} EUR", RIGHT)))
    summary.append((_p("UKUPNO", RIGHT_BOLD), _p(f"{fmt_money(result.total)} EUR", RIGHT_BOLD)))
    story.append(
        Table(
            summary,
            colWidths=[60 * mm, 36 * mm],
            hAlign="RIGHT",
            style=TableStyle([("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black)]),
        )
    )
    story.append(Spacer(1, 8 * mm))

    # --- napomene ---
    for text in (document.note, company.footer_note):
        if text:
            story.append(_p(text))
            story.append(Spacer(1, 3 * mm))

    # --- plaćanje ---
    if is_invoice and document.status == Document.Status.ISSUED and result.total > 0:
        reference = document.number.replace("/", "-")
        story.append(Spacer(1, 4 * mm))
        story.append(_p("PODACI ZA PLAĆANJE", SMALL))
        story.append(_p(f"IBAN: {company.iban}\nModel i poziv na broj: HR00 {reference}"))
        story.append(Spacer(1, 2 * mm))
        story.append(Barcode(hub3.modules(payment_payload(document, company))))
        story.append(_p("Skenirajte barkod aplikacijom svoje banke.", SMALL))

    if not draft:
        story.append(Spacer(1, 6 * mm))
        signer = company.owner or company.name
        story.append(
            _p(
                f"Dokument izdao: {signer}. Izrađeno na računalu, vrijedi bez potpisa i pečata.",
                SMALL,
            )
        )

    buffer = io.BytesIO()
    title = f"{name} {document.number}".strip()
    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
        author=company.name,
    ).build(story)
    return buffer.getvalue()
