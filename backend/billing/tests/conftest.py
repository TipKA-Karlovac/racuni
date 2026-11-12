from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from billing import services
from billing.models import Client, Company, Document

Kind = Document.Kind


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def company(db):
    company = Company.load()
    company.name = "Primjer, obrt"
    company.owner = "Ivan Primjer"
    company.address = "Radnička cesta 1"
    company.city = "47000 Karlovac"
    company.oib = "12345678903"
    company.iban = "HR3799999990000000001"
    company.save()
    return company


@pytest.fixture
def vat_company(company):
    company.vat_registered = True
    company.save()
    return company


@pytest.fixture
def client_a(db):
    return Client.objects.create(
        name="Pekara Klas d.o.o.", address="Ulica žita 5", city="47000 Karlovac", oib="11111111119"
    )


@pytest.fixture
def api(django_user_model):
    """Klijent API-ja prijavljen kao vlasnik."""
    user = django_user_model.objects.create_user("vlasnik", password="tajna-lozinka", is_staff=True)
    client = APIClient()
    client.force_login(user)
    return client


def tomorrow() -> date:
    return timezone.localdate() + timedelta(days=1)


def item(description="Usluga", quantity="1", unit_price="100", **extra) -> dict:
    return {
        "description": description,
        "quantity": Decimal(quantity),
        "unit_price": Decimal(unit_price),
        **{key: Decimal(value) if key != "unit" else value for key, value in extra.items()},
    }


def make_draft(client, kind=Kind.INVOICE, items=None, **data):
    return services.save_draft(
        document=None,
        data={"kind": kind, "client": client, "due_date": tomorrow(), **data},
        items=items if items is not None else [item()],
    )
