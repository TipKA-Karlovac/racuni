from rest_framework import serializers

from . import money
from .models import Client, Company, Document, Item
from .validators import normalize_iban


class CompanySerializer(serializers.ModelSerializer):
    missing_for_issuing = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Company
        exclude = ["id"]

    def validate_iban(self, value):
        return normalize_iban(value)

    def to_internal_value(self, data):
        # IBAN se smije upisati s razmacima; duljina se provjerava tek nakon čišćenja.
        if isinstance(data.get("iban"), str):
            data = {**data, "iban": normalize_iban(data["iban"])}
        return super().to_internal_value(data)


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ["id", "name", "address", "city", "oib", "email", "archived"]


class ItemSerializer(serializers.ModelSerializer):
    amount = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            "description",
            "unit",
            "quantity",
            "unit_price",
            "discount_percent",
            "vat_rate",
            "amount",
        ]
        extra_kwargs = {
            "unit": {"required": False},
            "discount_percent": {"required": False},
            "vat_rate": {"required": False},
        }

    def get_amount(self, item) -> str:
        return money.as_text(money.line_net(item.quantity, item.unit_price, item.discount_percent))

    def validate_vat_rate(self, value):
        if value not in Item.VAT_RATES:
            raise serializers.ValidationError("Stopa PDV-a može biti 0, 5, 13 ili 25 %.")
        return value


class DocumentListSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "kind",
            "status",
            "number",
            "client_name",
            "issue_date",
            "due_date",
            "total",
        ]

    def get_client_name(self, document) -> str:
        return document.buyer_name or document.client.name


class DocumentSerializer(serializers.ModelSerializer):
    """Cijeli dokument. Upisuju se samo polja nacrta; sve ostalo postavljaju pravila."""

    items = ItemSerializer(many=True)
    client = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all())
    client_name = serializers.SerializerMethodField()
    vat_breakdown = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "kind",
            "status",
            "number",
            "client",
            "client_name",
            "buyer_name",
            "buyer_address",
            "buyer_city",
            "buyer_oib",
            "issue_date",
            "delivery_date",
            "due_date",
            "note",
            "source",
            "items",
            "net_total",
            "vat_total",
            "total",
            "vat_breakdown",
        ]
        read_only_fields = [
            "status",
            "number",
            "buyer_name",
            "buyer_address",
            "buyer_city",
            "buyer_oib",
            "issue_date",
            "source",
            "net_total",
            "vat_total",
            "total",
        ]

    def get_client_name(self, document) -> str:
        return document.buyer_name or document.client.name

    def get_vat_breakdown(self, document) -> list[dict]:
        result = money.totals(document.items.all(), vat_registered=Company.load().vat_registered)
        return [
            {
                "rate": money.as_text(line.rate),
                "base": money.as_text(line.base),
                "vat": money.as_text(line.vat),
            }
            for line in result.by_rate
        ]

    def validate_items(self, items):
        if len(items) > 100:
            raise serializers.ValidationError("Dokument može imati najviše 100 stavki.")
        return items

    def validate(self, data):
        if self.instance is not None and "kind" in data and data["kind"] != self.instance.kind:
            raise serializers.ValidationError({"kind": "Vrsta dokumenta se ne može promijeniti."})
        return data


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, trim_whitespace=False)
