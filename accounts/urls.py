from django.contrib.auth.views import LogoutView
from django.urls import path
from .views import EmailLoginView, profile, register

app_name = "accounts"
urlpatterns = [
    path("register/", register, name="register"),
    path("login/", EmailLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", profile, name="profile"),
]
