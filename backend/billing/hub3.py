"""2D barkod za plaćanje (PDF417) prema uputi HUB-a za obrazac HUB 3A, verzija 6.

Zapis ima 14 polja, svako završava znakom LF. Barkod ima 9 podatkovnih
stupaca, razinu ispravljanja pogreške 4 i binarno kodiranje u UTF-8.
"""

from __future__ import annotations

import math
from decimal import Decimal

COLUMNS = 9
SECURITY_LEVEL = 4

_LETTERS = "abcčćdđefghijklmnoprsštuvzžqwxy"
_ALLOWED = frozenset("0123456789" + _LETTERS + _LETTERS.upper() + " ,.:-+?'/()")


def _text(value: str, limit: int) -> str:
    """Izbacuje znakove koje uputa ne dopušta i skraćuje na duljinu polja."""
    cleaned = "".join(char if char in _ALLOWED else " " for char in value)
    return " ".join(cleaned.split())[:limit].rstrip()


def payload(
    *,
    amount: Decimal,
    payer_name: str,
    payer_address: str,
    payer_city: str,
    recipient_name: str,
    recipient_address: str,
    recipient_city: str,
    iban: str,
    reference: str,
    description: str,
) -> str:
    cents = int(amount * 100)
    if not 0 <= cents < 10**15:
        raise ValueError("Iznos je izvan raspona koji stane u barkod.")
    reference = "".join(
        char for char in reference if char.isascii() and (char.isdigit() or char == "-")
    )
    fields = [
        "HRVHUB30",
        "EUR",
        f"{cents:015d}",
        _text(payer_name, 30),
        _text(payer_address, 27),
        _text(payer_city, 27),
        _text(recipient_name, 25),
        _text(recipient_address, 25),
        _text(recipient_city, 27),
        iban,
        "HR00" if reference else "HR99",
        reference[:22],
        "",  # šifra namjene nije obavezna
        _text(description, 35),
    ]
    return "".join(value + "\n" for value in fields)


def modules(text: str) -> list[str]:
    """Kodira zapis u PDF417 i vraća retke modula: ``"1"`` je crta, ``"0"`` praznina.

    ``pdf417gen.encode`` sam bira način sažimanja, a uputa traži isključivo
    binarno. Zato se kodne riječi slažu ovdje, a iz biblioteke se uzimaju
    sažimanje bajtova, Reed-Solomon ispravljanje i tablice uzoraka.
    """
    from pdf417gen.compaction.byte import compact_bytes
    from pdf417gen.encoding import encode_rows, get_padding
    from pdf417gen.error_correction import compute_error_correction_code_words

    data = text.encode("utf-8")
    latch = 924 if len(data) % 6 == 0 else 901
    data_words = [latch, *compact_bytes(data)]
    correction_count = 2 ** (SECURITY_LEVEL + 1)
    padding = get_padding(len(data_words), correction_count, COLUMNS)
    words = [len(data_words) + len(padding) + 1, *data_words, *padding]
    words += compute_error_correction_code_words(words, SECURITY_LEVEL)

    row_count = math.ceil(len(words) / COLUMNS)
    rows = [words[i * COLUMNS : (i + 1) * COLUMNS] for i in range(row_count)]
    codes = encode_rows(rows, COLUMNS, SECURITY_LEVEL)
    return ["".join(format(word, "b") for word in row) for row in codes]
