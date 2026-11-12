from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError

from billing import money
from billing.pdf import fmt_money, fmt_quantity
from billing.validators import validate_iban, validate_oib


def line(quantity, unit_price, discount="0", vat="25"):
    return SimpleNamespace(
        quantity=D(quantity),
        unit_price=D(unit_price),
        discount_percent=D(discount),
        vat_rate=D(vat),
    )


@pytest.mark.parametrize(
    ("quantity", "price", "discount", "expected"),
    [
        ("1", "100", "0", "100.00"),
        ("2.5", "30", "0", "75.00"),
        ("12", "25", "10", "270.00"),
        ("3", "0.335", "0", "1.01"),  # 1,005 → pola se zaokružuje prema gore
        ("1", "0.125", "0", "0.13"),
        ("1", "0.124", "0", "0.12"),
        ("1", "99.99", "100", "0.00"),
        ("0.333", "10", "0", "3.33"),
    ],
)
def test_line_amount_rounds_half_up_to_cents(quantity, price, discount, expected):
    assert money.line_net(D(quantity), D(price), D(discount)) == D(expected)


def test_vat_is_calculated_per_rate_not_per_line():
    # Tri stavke po 0,10 EUR uz 25 %: po stavci bi PDV bio 3 × 0,03 = 0,09,
    # a na osnovicu 0,30 iznosi 0,08 (0,075 zaokruženo).
    result = money.totals([line("1", "0.10")] * 3, vat_registered=True)
    assert (result.net, result.vat, result.total) == (D("0.30"), D("0.08"), D("0.38"))


def test_totals_group_by_vat_rate():
    items = [line("1", "100", vat="25"), line("2", "50", vat="13"), line("1", "40", vat="25")]
    result = money.totals(items, vat_registered=True)
    assert [(v.rate, v.base, v.vat) for v in result.by_rate] == [
        (D("13"), D("100.00"), D("13.00")),
        (D("25"), D("140.00"), D("35.00")),
    ]
    assert (result.net, result.vat, result.total) == (D("240.00"), D("48.00"), D("288.00"))


def test_issuer_outside_the_vat_system_charges_no_vat():
    result = money.totals([line("1", "100", vat="25")], vat_registered=False)
    assert (result.net, result.vat, result.total) == (D("100.00"), D("0"), D("100.00"))
    assert [(v.rate, v.vat) for v in result.by_rate] == [(D("0"), D("0.00"))]


def test_no_items_means_zero():
    result = money.totals([], vat_registered=True)
    assert (result.net, result.vat, result.total, result.by_rate) == (D("0"), D("0"), D("0"), [])


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0", "0,00"), ("5.5", "5,50"), ("1234.5", "1.234,50"), ("1234567.891", "1.234.567,89")],
)
def test_money_is_written_the_croatian_way(value, expected):
    assert fmt_money(D(value)) == expected


@pytest.mark.parametrize(
    ("value", "expected"), [("1.000", "1"), ("2.500", "2,5"), ("0.125", "0,125")]
)
def test_quantity_drops_trailing_zeros(value, expected):
    assert fmt_quantity(D(value)) == expected


# Javno objavljeni OIB-i hrvatskih tvrtki i ustanova – neovisna potvrda postupka.
@pytest.mark.parametrize("oib", ["85821130368", "81793146560", "92963223473", "12345678903"])
def test_valid_oib(oib):
    validate_oib(oib)


@pytest.mark.parametrize("oib", ["85821130369", "8582113036", "858211303680", "8582113036A", ""])
def test_invalid_oib(oib):
    with pytest.raises(ValidationError):
        validate_oib(oib)


@pytest.mark.parametrize(
    "iban", ["HR1210010051863000160", "hr12 1001 0051 8630 0016 0", "HR3799999990000000001"]
)
def test_valid_iban(iban):
    validate_iban(iban)


@pytest.mark.parametrize(
    "iban", ["HR1210010051863000161", "HR121001005186300016", "DE89370400440532013000", ""]
)
def test_invalid_iban(iban):
    with pytest.raises(ValidationError):
        validate_iban(iban)
