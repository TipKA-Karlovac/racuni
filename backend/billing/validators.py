"""Provjere hrvatskih identifikatora: OIB i IBAN."""

from django.core.exceptions import ValidationError


def validate_oib(value: str) -> None:
    """OIB ima 11 znamenaka; zadnja je kontrolna prema ISO 7064, MOD 11,10."""
    if not (value.isascii() and value.isdigit() and len(value) == 11):
        raise ValidationError("OIB mora imati točno 11 znamenaka.")
    remainder = 10
    for digit in value[:10]:
        remainder = (remainder + int(digit)) % 10 or 10
        remainder = (remainder * 2) % 11
    if (11 - remainder) % 10 != int(value[10]):
        raise ValidationError("OIB nije ispravan. Provjerite jeste li ga točno prepisali.")


def normalize_iban(value: str) -> str:
    return "".join(value.split()).upper()


def validate_iban(value: str) -> None:
    """Hrvatski IBAN: HR, 19 znamenaka i kontrolni broj prema MOD 97."""
    iban = normalize_iban(value)
    if not (iban.isascii() and len(iban) == 21 and iban[:2] == "HR" and iban[2:].isdigit()):
        raise ValidationError("IBAN mora biti hrvatski: HR i 19 znamenaka.")
    rearranged = iban[4:] + "1727" + iban[2:4]  # H=17, R=27
    if int(rearranged) % 97 != 1:
        raise ValidationError("IBAN nije ispravan. Provjerite jeste li ga točno prepisali.")
