from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("clients", views.ClientViewSet, basename="client")
router.register("documents", views.DocumentViewSet, basename="document")

urlpatterns = [
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("company/", views.CompanyView.as_view(), name="company"),
    path("summary/", views.SummaryView.as_view(), name="summary"),
    path("", include(router.urls)),
]
