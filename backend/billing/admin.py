from django.contrib import admin

from .models import Client, Company, Document, Item


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not Company.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "oib", "archived"]
    search_fields = ["name", "oib"]


class ItemInline(admin.TabularInline):
    model = Item
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Samo pregled: dokumenti nastaju i mijenjaju se kroz aplikaciju, gdje vrijede pravila."""

    list_display = ["number", "kind", "status", "client", "issue_date", "total"]
    list_filter = ["kind", "status", "year"]
    search_fields = ["number", "buyer_name", "client__name"]
    inlines = [ItemInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
