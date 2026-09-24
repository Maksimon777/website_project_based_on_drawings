from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms import DUPLICATE_EMAIL, EmailAuthenticationForm, ProfileForm, RegistrationForm


def save_form(form):
    try:
        with transaction.atomic():
            form.save()
    except IntegrityError as error:
        # The unique index also protects simultaneous registrations and email edits.
        constraint = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
        if constraint != "accounts_unique_email_ci":
            raise
        form.add_error("email", DUPLICATE_EMAIL)
        return False
    return True


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm


@never_cache
@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid() and save_form(form):
        messages.success(request, "Аккаунт создан. Теперь войдите по email и паролю.")
        return redirect("accounts:login")
    return render(request, "accounts/register.html", {"form": form})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    form = ProfileForm(request.POST if request.method == "POST" else None, instance=request.user)
    if request.method == "POST" and form.is_valid() and save_form(form):
        messages.success(request, "Профиль сохранён.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})
