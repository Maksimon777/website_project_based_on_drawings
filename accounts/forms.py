from uuid import uuid4

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User

DUPLICATE_EMAIL = "Этот email уже зарегистрирован. Войдите в существующий аккаунт."


class ContactFormMixin:
    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        existing = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError(DUPLICATE_EMAIL)
        return email


class RegistrationForm(ContactFormMixin, UserCreationForm):
    first_name = forms.CharField(label="Имя", max_length=150)
    email = forms.EmailField(label="Email", max_length=254)

    class Meta:
        model = User
        fields = ("first_name", "email")

    def save(self, commit=True):
        user = super().save(commit=False)
        # Internal username preserves the existing admin login and user references.
        user.username = uuid4().hex
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email", max_length=254,
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )
    error_messages = {
        "invalid_login": "Неверный email или пароль.",
        "inactive": "Вход в этот аккаунт недоступен.",
    }

    def clean(self):
        email = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if email and password:
            self.user_cache = authenticate(self.request, email=email, password=password)
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class ProfileForm(ContactFormMixin, forms.ModelForm):
    first_name = forms.CharField(label="Имя", max_length=150)
    email = forms.EmailField(label="Email", max_length=254)
    current_password = forms.CharField(
        label="Текущий пароль — только при смене email",
        required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    class Meta:
        model = User
        fields = ("first_name", "email", "telegram", "delivery_method")
        help_texts = {"telegram": "Необязательно. Например, @my_username."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_email = self.instance.email.lower()

    def clean_telegram(self):
        return self.cleaned_data["telegram"].strip()

    def clean(self):
        data = super().clean()
        email = data.get("email")
        if email and email != self.original_email:
            if not self.instance.check_password(data.get("current_password", "")):
                self.add_error("current_password", "Для смены email введите верный текущий пароль.")
        if data.get("delivery_method") == User.DeliveryMethod.TELEGRAM and not data.get("telegram"):
            self.add_error("telegram", "Укажите Telegram для выбранного способа получения.")
        return data
