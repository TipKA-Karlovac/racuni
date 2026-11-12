from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from .validators import validate_iban, validate_oib

ZERO = Decimal("0")


class Company(models.Model):
    """Podaci izdavatelja. Postoji točno jedan zapis (pk=1)."""

    name = models.CharField("naziv", max_length=120, blank=True)
    owner = models.CharField("vlasnik", max_length=80, blank=True)
    address = models.CharField("adresa", max_length=120, blank=True)
    city = models.CharField("poštanski broj i mjesto", max_length=80, blank=True)
    oib = models.CharField("OIB", max_length=11, blank=True, validators=[validate_oib])
    iban = models.CharField("IBAN", max_length=21, blank=True, validators=[validate_iban])
    email = models.EmailField("e-pošta", blank=True)
    phone = models.CharField("telefon", max_length=30, blank=True)

    vat_registered = models.BooleanField("u sustavu PDV-a", default=False)
    premise_code = models.CharField("oznaka poslovnog prostora", max_length=10, default="1")
    device_code = models.CharField("oznaka naplatnog uređaja", max_length=10, default="1")
    due_days = models.PositiveSmallIntegerField(
        "rok plaćanja (dana)", default=15, validators=[MaxValueValidator(365)]
    )
    footer_note = models.TextField("napomena na dnu dokumenta", max_length=600, blank=True)

    class Meta:
        verbose_name = "izdavatelj"
        verbose_name_plural = "izdavatelj"

    def __str__(self):
        return self.name or "Izdavatelj"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "Company":
        company, _ = cls.objects.get_or_create(pk=1)
        return company

    def missing_for_issuing(self) -> list[str]:
        """Nazivi obaveznih polja koja još nisu upisana."""
        required = {
            "naziv": self.name,
            "adresa": self.address,
            "mjesto": self.city,
            "OIB": self.oib,
            "IBAN": self.iban,
        }
        return [label for label, value in required.items() if not value]


class Client(models.Model):
    name = models.CharField("naziv ili ime i prezime", max_length=120)
    address = models.CharField("adresa", max_length=120, blank=True)
    city = models.CharField("poštanski broj i mjesto", max_length=80, blank=True)
    oib = models.CharField("OIB", max_length=11, blank=True, validators=[validate_oib])
    email = models.EmailField("e-pošta", blank=True)
    archived = models.BooleanField("arhiviran", default=False)

    class Meta:
        ordering = ["name"]
        verbose_name = "klijent"
        verbose_name_plural = "klijenti"

    def __str__(self):
        return self.name


class Counter(models.Model):
    """Zadnji izdani redni broj za vrstu dokumenta u godini."""

    kind = models.CharField(max_length=10)
    year = models.PositiveSmallIntegerField()
    last = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "year"], name="counter_kind_year")]

    def __str__(self):
        return f"{self.kind} {self.year}: {self.last}"


class Document(models.Model):
    """Ponuda ili račun.

    Nacrt se slobodno uređuje i briše. Izdavanjem dobiva broj i datum, a
    podaci kupca se prepisuju u dokument – izdani dokument se više ne mijenja,
    može se samo stornirati. Broj storniranog dokumenta se ne koristi ponovno.
    """

    class Kind(models.TextChoices):
        QUOTE = "quote", "ponuda"
        INVOICE = "invoice", "račun"

    class Status(models.TextChoices):
        DRAFT = "draft", "nacrt"
        ISSUED = "issued", "izdano"
        PAID = "paid", "plaćeno"
        ACCEPTED = "accepted", "prihvaćeno"
        REJECTED = "rejected", "odbijeno"
        CANCELLED = "cancelled", "stornirano"

    kind = models.CharField("vrsta", max_length=10, choices=Kind.choices)
    status = models.CharField("status", max_length=10, choices=Status.choices, default=Status.DRAFT)

    year = models.PositiveSmallIntegerField(null=True, blank=True, editable=False)
    sequence = models.PositiveIntegerField(null=True, blank=True, editable=False)
    number = models.CharField("broj", max_length=30, blank=True, editable=False)

    client = models.ForeignKey(
        Client, verbose_name="klijent", on_delete=models.PROTECT, related_name="documents"
    )
    # Prijepis podataka kupca u trenutku izdavanja.
    buyer_name = models.CharField(max_length=120, blank=True)
    buyer_address = models.CharField(max_length=120, blank=True)
    buyer_city = models.CharField(max_length=80, blank=True)
    buyer_oib = models.CharField(max_length=11, blank=True)

    issue_date = models.DateField("datum izdavanja", null=True, blank=True)
    delivery_date = models.DateField("datum isporuke", null=True, blank=True)
    due_date = models.DateField("rok plaćanja / vrijedi do")
    note = models.TextField("napomena", max_length=600, blank=True)

    source = models.ForeignKey(
        "self",
        verbose_name="nastalo iz ponude",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )

    net_total = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    vat_total = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)

    created_at = models.DateTimeField(auto_now_add=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "dokument"
        verbose_name_plural = "dokumenti"
        constraints = [
            # Dva dokumenta iste vrste ne mogu dobiti isti broj u istoj godini.
            models.UniqueConstraint(
                fields=["kind", "year", "sequence"],
                condition=Q(sequence__isnull=False),
                name="document_unique_number",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.number or '(nacrt)'}"

    @property
    def is_draft(self) -> bool:
        return self.status == self.Status.DRAFT


class Item(models.Model):
    VAT_RATES = [Decimal("0"), Decimal("5"), Decimal("13"), Decimal("25")]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveSmallIntegerField(default=0)
    description = models.CharField("opis", max_length=200)
    unit = models.CharField("jedinica", max_length=10, default="kom")
    quantity = models.DecimalField(
        "količina",
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    unit_price = models.DecimalField(
        "cijena", max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )
    discount_percent = models.DecimalField(
        "popust (%)",
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal("100"))],
    )
    # Dopuštene stope provjerava serializer (Item.VAT_RATES).
    vat_rate = models.DecimalField("PDV (%)", max_digits=4, decimal_places=2, default=ZERO)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "stavka"
        verbose_name_plural = "stavke"

    def __str__(self):
        return self.description
