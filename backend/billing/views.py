from django.contrib.auth import authenticate, login, logout
from django.db.models import ProtectedError, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import money, pdf, services
from .models import Client, Company, Document
from .serializers import (
    ClientSerializer,
    CompanySerializer,
    DocumentListSerializer,
    DocumentSerializer,
    LoginSerializer,
)

Kind = Document.Kind
Status = Document.Status


def _rule_error(exc: services.RuleError) -> Response:
    return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)


# --- prijava -----------------------------------------------------------------


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(APIView):
    """Tko je prijavljen. Usput postavlja CSRF kolačić potreban za prijavu."""

    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user
        is_owner = user.is_authenticated and user.is_staff
        return Response({"authenticated": is_owner, "username": user.username if is_owner else ""})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, **serializer.validated_data)
        if user is None or not user.is_staff:
            return Response(
                {"detail": "Pogrešno korisničko ime ili lozinka."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        return Response({"authenticated": True, "username": user.username})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"authenticated": False, "username": ""})


# --- izdavatelj i pregled ----------------------------------------------------


class CompanyView(APIView):
    def get(self, request):
        return Response(CompanySerializer(Company.load()).data)

    def put(self, request):
        serializer = CompanySerializer(Company.load(), data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SummaryView(APIView):
    """Brojke za početnu stranicu: što je nenaplaćeno, što kasni, koliko je izdano ove godine."""

    def get(self, request):
        today = timezone.localdate()
        invoices = Document.objects.filter(kind=Kind.INVOICE)
        unpaid = invoices.filter(status=Status.ISSUED)
        overdue = unpaid.filter(due_date__lt=today)
        this_year = invoices.filter(year=today.year, status__in=[Status.ISSUED, Status.PAID])

        def total(queryset):
            return money.as_text(queryset.aggregate(sum=Sum("total"))["sum"] or 0)

        return Response(
            {
                "unpaid_total": total(unpaid),
                "unpaid_count": unpaid.count(),
                "overdue_total": total(overdue),
                "overdue_count": overdue.count(),
                "invoiced_this_year": total(this_year),
                "open_quotes": Document.objects.filter(
                    kind=Kind.QUOTE, status=Status.ISSUED
                ).count(),
            }
        )


# --- klijenti ----------------------------------------------------------------


class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = Client.objects.all()
        if self.action == "list" and self.request.query_params.get("archived") != "1":
            queryset = queryset.filter(archived=False)
        return queryset

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "Klijent ima dokumente pa se ne može obrisati. Možete ga arhivirati."},
                status=status.HTTP_409_CONFLICT,
            )


# --- dokumenti ---------------------------------------------------------------


class DocumentViewSet(viewsets.ModelViewSet):
    pagination_class = None
    http_method_names = ["get", "post", "put", "delete", "head", "options"]

    def get_queryset(self):
        queryset = Document.objects.select_related("client").prefetch_related("items")
        if self.action != "list":
            return queryset
        params = self.request.query_params
        if params.get("kind") in Kind.values:
            queryset = queryset.filter(kind=params["kind"])
        if params.get("status") in Status.values:
            queryset = queryset.filter(status=params["status"])
        if params.get("overdue") == "1":
            queryset = queryset.filter(
                kind=Kind.INVOICE, status=Status.ISSUED, due_date__lt=timezone.localdate()
            )
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(number__icontains=search)
                | Q(client__name__icontains=search)
                | Q(buyer_name__icontains=search)
            )
        return queryset

    def get_serializer_class(self):
        return DocumentListSerializer if self.action == "list" else DocumentSerializer

    def _save(self, request, document):
        serializer = DocumentSerializer(document, data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        items = data.pop("items")
        try:
            saved = services.save_draft(document=document, data=data, items=items)
        except services.RuleError as exc:
            return _rule_error(exc)
        code = status.HTTP_201_CREATED if document is None else status.HTTP_200_OK
        return Response(DocumentSerializer(self.get_queryset().get(pk=saved.pk)).data, status=code)

    def create(self, request, *args, **kwargs):
        return self._save(request, None)

    def update(self, request, *args, **kwargs):
        return self._save(request, self.get_object())

    def destroy(self, request, *args, **kwargs):
        try:
            services.delete_draft(self.get_object())
        except services.RuleError as exc:
            return _rule_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _run(self, function, **kwargs):
        """Izvršava poslovnu radnju nad dokumentom i vraća njegovo novo stanje."""
        try:
            result = function(self.get_object(), **kwargs)
        except services.RuleError as exc:
            return _rule_error(exc)
        return Response(DocumentSerializer(self.get_queryset().get(pk=result.pk)).data)

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        return self._run(services.issue)

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        return self._run(services.mark_paid)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        return self._run(services.set_quote_outcome, accepted=True)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._run(services.set_quote_outcome, accepted=False)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._run(services.cancel)

    @action(detail=True, methods=["post"], url_path="to-invoice")
    def to_invoice(self, request, pk=None):
        return self._run(services.quote_to_invoice)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        document = self.get_object()
        name = "racun" if document.kind == Kind.INVOICE else "ponuda"
        suffix = document.number.replace("/", "-") or "nacrt"
        response = HttpResponse(pdf.render(document), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{name}-{suffix}.pdf"'
        return response
