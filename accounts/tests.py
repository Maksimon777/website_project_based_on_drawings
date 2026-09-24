from unittest.mock import patch

from django.db import IntegrityError, OperationalError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .models import User

PASSWORD = "Drawing-test-Passphrase-829!"


class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("existing", email="owner@example.com", password=PASSWORD)
        cls.other = User.objects.create_user("other", email="other@example.com", password=PASSWORD)

    def registration(self, **overrides):
        data = {"first_name": "Анна", "email": "new@example.com",
                "password1": PASSWORD, "password2": PASSWORD}
        data.update(overrides)
        return self.client.post(reverse("accounts:register"), data)

    def login(self, **overrides):
        data = {"username": self.user.email, "password": PASSWORD}
        data.update(overrides)
        return self.client.post(reverse("accounts:login"), data)

    def profile_data(self, **overrides):
        data = {"first_name": "Анна", "email": self.user.email,
                "telegram": "", "delivery_method": "email"}
        data.update(overrides)
        return data

    def test_registration_hashes_password_and_does_not_grant_staff(self):
        response = self.registration(email="NEW@EXAMPLE.COM", is_staff="true")
        self.assertRedirects(response, reverse("accounts:login"))
        user = User.objects.get(email="new@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_duplicate_email_case_insensitive(self):
        response = self.registration(email="OWNER@EXAMPLE.COM")
        self.assertContains(response, "Этот email уже зарегистрирован")
        self.assertEqual(User.objects.count(), 2)

    def test_database_rejects_duplicate_email(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("duplicate", email="OWNER@example.com", password=PASSWORD)

    def test_invalid_registration_data(self):
        for override in [
            {"email": "invalid"}, {"first_name": " "},
            {"password2": "different"}, {"password1": "123", "password2": "123"},
        ]:
            with self.subTest(override=override):
                response = self.registration(**override)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertEqual(User.objects.count(), 2)

    def test_email_login_case_insensitive(self):
        self.assertRedirects(self.login(username="OWNER@EXAMPLE.COM"), reverse("accounts:profile"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_wrong_password_and_inactive_account(self):
        self.assertContains(self.login(password="wrong"), "Неверный email или пароль")
        self.user.is_active = False
        self.user.save()
        self.assertContains(self.login(), "Неверный email или пароль")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_external_login_redirect_is_rejected(self):
        self.assertRedirects(self.login(next="https://example.org/"), reverse("accounts:profile"))

    def test_profile_requires_login(self):
        self.assertRedirects(self.client.get(reverse("accounts:profile")),
                             reverse("accounts:login") + "?next=" + reverse("accounts:profile"))

    def test_profile_updates_only_self(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:profile"),
            self.profile_data(telegram="@anna_test", delivery_method="telegram",
                              id=self.other.pk, is_staff="true"))
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.user.telegram, "@anna_test")
        self.assertFalse(self.user.is_staff)
        self.assertEqual(self.other.telegram, "")

    def test_telegram_required_when_selected(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:profile"), self.profile_data(delivery_method="telegram"))
        self.assertIn("telegram", response.context["form"].errors)
        response = self.client.post(reverse("accounts:profile"), self.profile_data(telegram="bad contact"))
        self.assertIn("telegram", response.context["form"].errors)

    def test_email_change_requires_password_and_changes_login(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:profile"), self.profile_data(email="changed@example.com"))
        self.assertIn("current_password", response.context["form"].errors)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "owner@example.com")
        response = self.client.post(reverse("accounts:profile"),
            self.profile_data(email="changed@example.com", current_password=PASSWORD))
        self.assertRedirects(response, reverse("accounts:profile"))
        self.client.logout()
        self.assertContains(self.login(), "Неверный email или пароль")
        self.assertRedirects(self.login(username="changed@example.com"), reverse("accounts:profile"))

    def test_profile_cannot_take_another_email(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:profile"),
            self.profile_data(email="OTHER@EXAMPLE.COM", current_password=PASSWORD))
        self.assertIn("email", response.context["form"].errors)

    def test_logout_requires_post_and_clears_session(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("accounts:logout")), reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        for name in ["register", "login", "profile", "logout"]:
            with self.subTest(name=name):
                self.assertEqual(client.post(reverse("accounts:" + name), {}).status_code, 403)

    def test_database_failure_is_explicit_without_private_details(self):
        with patch("accounts.forms.User.objects.filter", side_effect=OperationalError("private-details")):
            with self.assertLogs("accounts", level="ERROR") as logs:
                response = self.registration()
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, "private-details", status_code=503)
        self.assertNotIn("private-details", " ".join(logs.output))
        self.assertEqual(User.objects.count(), 2)

    def test_existing_admin_username_login_still_works(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(reverse("admin:login"), {
            "username": self.user.username, "password": PASSWORD, "next": reverse("admin:index")})
        self.assertRedirects(response, reverse("admin:index"))
