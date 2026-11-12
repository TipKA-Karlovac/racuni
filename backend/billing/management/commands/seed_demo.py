from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from billing import services
from billing.models import Client, Company, Document

# Izmišljeni podaci. OIB-i i IBAN imaju ispravne kontrolne znamenke, ali ne
# pripadaju stvarnim osobama ni tvrtkama iz ovog primjera.
COMPANY = {
    "name": "Primjer, obrt za računalne usluge",
    "owner": "Ivan Primjer",
    "address": "Radnička cesta 1",
    "city": "47000 Karlovac",
    "oib": "12345678903",
    "iban": "HR3799999990000000001",
    "email": "info@primjer.example",
    "phone": "047 000 000",
    "footer_note": (
        "Obveznik nije u sustavu PDV-a. PDV nije obračunat temeljem članka 90. "
        "stavka 2. Zakona o porezu na dodanu vrijednost."
    ),
}

CLIENTS = [
    {"name": "Pekara Klas d.o.o.", "address": "Ulica žita 5", "city": "47000 Karlovac"},
    {"name": "Ana Anić", "address": "Riječka 12", "city": "47000 Karlovac"},
]


class Command(BaseCommand):
    help = "Puni bazu primjerom: izdavatelj, klijenti, jedna ponuda i dva računa."

    def add_arguments(self, parser):
        parser.add_argument("--owner", metavar="KORISNIK", help="Stvori korisnika vlasnika.")

    def handle(self, *args, **options):
        company = Company.load()
        if not company.name:
            for field, value in COMPANY.items():
                setattr(company, field, value)
            company.save()

        if not Client.objects.exists():
            bakery, person = (Client.objects.create(**data) for data in CLIENTS)
            due = timezone.localdate() + timedelta(days=company.due_days)

            def draft(kind, client, items):
                return services.save_draft(
                    document=None,
                    data={"kind": kind, "client": client, "due_date": due},
                    items=items,
                )

            web = [
                {
                    "description": "Izrada web stranice",
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("900"),
                },
                {
                    "description": "Održavanje",
                    "unit": "mj",
                    "quantity": Decimal("12"),
                    "unit_price": Decimal("25"),
                    "discount_percent": Decimal("10"),
                },
            ]
            services.issue(draft(Document.Kind.QUOTE, bakery, web))
            services.issue(draft(Document.Kind.INVOICE, bakery, web[:1]))
            draft(
                Document.Kind.INVOICE,
                person,
                [
                    {
                        "description": "Servis računala",
                        "unit": "h",
                        "quantity": Decimal("2.5"),
                        "unit_price": Decimal("30"),
                    }
                ],
            )
        self.stdout.write(self.style.SUCCESS("Primjer podataka je upisan."))

        if options["owner"]:
            user, created = get_user_model().objects.get_or_create(
                username=options["owner"], defaults={"is_staff": True, "is_superuser": True}
            )
            if created:
                user.set_unusable_password()
                user.save()
                self.stdout.write(
                    f"Korisnik '{user.username}' je stvoren bez lozinke. Postavite je: "
                    f"python manage.py changepassword {user.username}"
                )
