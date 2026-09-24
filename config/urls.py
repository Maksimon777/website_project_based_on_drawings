from django.contrib import admin
from django.urls import include, path
from core.views import health, home

urlpatterns = [
    path("orders/", include("orders.urls")),
    path("accounts/", include("accounts.urls")),
    path("", home, name="home"),
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
]
