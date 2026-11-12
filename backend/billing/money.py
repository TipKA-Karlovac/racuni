"""Izračun iznosa. Sve u ``Decimal``, zaokruživanje na cent „pola prema gore”.

Pravila:

- iznos stavke = količina × cijena × (1 − popust), zaokružen na cent;
- osnovica po stopi PDV-a = zbroj iznosa stavki s tom stopom;
- PDV se računa na osnovicu po stopi (ne po stavci), pa zaokružen na cent;
- izdavatelj koji nije u sustavu PDV-a ne obračunava PDV.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0")
HUNDRED = Decimal("100")


def to_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def as_text(value: Decimal) -> str:
    """Iznos za JSON, uvijek s dvije decimale. Nikad float: 0.1 + 0.2 nije 0.3."""
    return f"{to_cents(Decimal(value)):.2f}"


def line_net(quantity: Decimal, unit_price: Decimal, discount_percent: Decimal = ZERO) -> Decimal:
    return to_cents(quantity * unit_price * (HUNDRED - discount_percent) / HUNDRED)


@dataclass(frozen=True)
class VatLine:
    rate: Decimal
    base: Decimal
    vat: Decimal


@dataclass(frozen=True)
class Totals:
    net: Decimal = ZERO
    vat: Decimal = ZERO
    total: Decimal = ZERO
    by_rate: list[VatLine] = field(default_factory=list)


def totals(items: Iterable, *, vat_registered: bool) -> Totals:
    """Zbraja stavke. Svaka stavka ima quantity, unit_price, discount_percent i vat_rate."""
    bases: dict[Decimal, Decimal] = {}
    for item in items:
        rate = item.vat_rate if vat_registered else ZERO
        net = line_net(item.quantity, item.unit_price, item.discount_percent)
        bases[rate] = bases.get(rate, ZERO) + net

    by_rate = [
        VatLine(rate=rate, base=base, vat=to_cents(base * rate / HUNDRED))
        for rate, base in sorted(bases.items())
    ]
    net = sum((line.base for line in by_rate), ZERO)
    vat = sum((line.vat for line in by_rate), ZERO)
    return Totals(net=net, vat=vat, total=net + vat, by_rate=by_rate)
