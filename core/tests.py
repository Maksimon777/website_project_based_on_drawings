from unittest.mock import patch
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class HealthTests(TestCase):
    def test_database_is_reachable(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})


class FailureTests(SimpleTestCase):
    def test_database_failure_is_not_reported_as_success(self):
        with patch("core.views.connection") as database:
            database.cursor.side_effect = OperationalError("private-details")
            with self.assertLogs("core", level="ERROR") as logs:
                response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["database"], "unavailable")
        self.assertNotIn("private-details", response.content.decode())
        self.assertNotIn("private-details", " ".join(logs.output))

    def test_home_page(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сервис заказов на чертежи")
