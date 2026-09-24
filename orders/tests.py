from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from .forms import OrderForm
from .models import Order, OrderFile, StatusHistory
from .services import OrderConflict, save_customer_order, update_by_staff


class OrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("customer", email="customer@example.com")
        cls.other = User.objects.create_user("stranger", email="stranger@example.com")
        cls.admin = User.objects.create_superuser("admin", email="admin@example.com", password="admin-test-only-859!")

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.directory.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.client.force_login(self.owner)

    def data(self, **changes):
        values = {
            "title": "Задание 1", "category": "geometry", "description": "Построить проекции",
            "teacher_requirements": "", "deadline": (timezone.localdate() + timedelta(days=7)).isoformat(),
            "output_formats": ["pdf", "print"], "other_format": "", "revision": 1,
        }
        values.update(changes)
        return values

    def pdf(self, name="task.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.7\n test source", content_type="application/pdf")

    def create(self, files=None):
        data = self.data()
        if files:
            data["files"] = files
        response = self.client.post(reverse("orders:create"), data)
        self.assertEqual(response.status_code, 302)
        return Order.objects.latest("pk")

    def staff_change(self, order, status, **kwargs):
        order.refresh_from_db()
        return update_by_staff(actor=self.admin, order_id=order.pk, status=status,
            assigned_to=kwargs.get("assigned_to", order.assigned_to),
            feedback=kwargs.get("feedback", ""), revision=order.revision)

    def test_create_with_multiple_files_and_history(self):
        order = self.create([self.pdf(), self.pdf()])
        self.assertEqual(order.owner, self.owner)
        self.assertEqual(order.status, Order.Status.SUBMITTED)
        self.assertEqual(order.files.count(), 2)
        paths = list(order.files.values_list("file", flat=True))
        self.assertNotEqual(paths[0], paths[1])
        self.assertEqual(order.history.count(), 1)

    def test_order_without_files(self):
        self.assertEqual(self.create().files.count(), 0)

    def test_required_fields_show_errors_and_red_class(self):
        response = self.client.post(reverse("orders:create"), {})
        self.assertContains(response, "Это поле обязательное.")
        self.assertContains(response, "field-error")
        self.assertEqual(Order.objects.count(), 0)

    def test_past_deadline_and_other_format_validation(self):
        response = self.client.post(reverse("orders:create"),
            self.data(deadline=(timezone.localdate() - timedelta(days=1)).isoformat(),
                      output_formats=["other"]))
        self.assertIn("deadline", response.context["form"].errors)
        self.assertIn("other_format", response.context["form"].errors)

    def test_unknown_choices_rejected(self):
        response = self.client.post(reverse("orders:create"), self.data(category="bad", output_formats=["bad"]))
        self.assertIn("category", response.context["form"].errors)
        self.assertIn("output_formats", response.context["form"].errors)

    def test_every_file_is_validated_before_saving(self):
        for name, content in [("bad.exe", b"MZ"), ("fake.pdf", b"MZ"), ("empty.pdf", b"")]:
            with self.subTest(name=name):
                response = self.client.post(reverse("orders:create"),
                    self.data(files=[self.pdf(), SimpleUploadedFile(name, content)]))
                self.assertIn("files", response.context["form"].errors)
                self.assertEqual(Order.objects.count(), 0)
                self.assertFalse(any(Path(self.directory.name).rglob("*.*")))

    def test_failed_second_upload_rolls_back_order_and_first_file(self):
        from django.core.files.storage import default_storage
        original = default_storage.save
        calls = 0
        def failing_save(name, content, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("disk unavailable")
            return original(name, content, *args, **kwargs)
        with patch.object(default_storage, "save", side_effect=failing_save):
            response = self.client.post(reverse("orders:create"), self.data(files=[self.pdf(), self.pdf()]))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderFile.objects.count(), 0)
        self.assertEqual(StatusHistory.objects.count(), 0)
        self.assertFalse(any(p.is_file() for p in Path(self.directory.name).rglob("*")))

    def test_customer_can_edit_submitted_and_append_file(self):
        order = self.create([self.pdf()])
        response = self.client.post(reverse("orders:edit", args=[order.pk]),
            self.data(title="Обновлено", files=[self.pdf("new.pdf")]))
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.title, "Обновлено")
        self.assertEqual(order.files.count(), 2)
        self.assertEqual(order.revision, 2)

    def test_review_locks_both_get_and_post(self):
        order = self.staff_change(self.create(), Order.Status.REVIEWING)
        url = reverse("orders:edit", args=[order.pk])
        self.assertEqual(self.client.get(url).status_code, 409)
        self.assertEqual(self.client.post(url, self.data(title="Запрещено")).status_code, 409)
        order.refresh_from_db()
        self.assertEqual(order.title, "Задание 1")

    def test_stale_customer_form_cannot_overwrite_staff_change(self):
        order = self.create()
        form = OrderForm(self.data(), instance=order)
        self.assertTrue(form.is_valid())
        self.staff_change(order, Order.Status.REVIEWING)
        with self.assertRaises(OrderConflict):
            save_customer_order(actor=self.owner, form=form, order_id=order.pk)

    def test_stale_customer_revision_rejected(self):
        order = self.create()
        self.client.post(reverse("orders:edit", args=[order.pk]), self.data(title="Новый текст"))
        response = self.client.post(reverse("orders:edit", args=[order.pk]), self.data(title="Старый текст"))
        self.assertEqual(response.status_code, 409)
        order.refresh_from_db()
        self.assertEqual(order.title, "Новый текст")

    def test_return_for_info_and_resubmission(self):
        order = self.staff_change(self.create(), Order.Status.REVIEWING)
        order = self.staff_change(order, Order.Status.NEEDS_INFO, feedback="Добавьте размеры")
        self.assertContains(self.client.get(reverse("orders:detail", args=[order.pk])), "Добавьте размеры")
        response = self.client.post(reverse("orders:edit", args=[order.pk]),
            self.data(description="Добавлены размеры", revision=order.revision))
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SUBMITTED)
        self.assertEqual(order.history.count(), 4)

    def test_work_requires_executor_and_valid_transitions(self):
        order = self.create()
        with self.assertRaises(ValidationError):
            self.staff_change(order, Order.Status.READY)
        order = self.staff_change(order, Order.Status.REVIEWING)
        with self.assertRaises(ValidationError):
            self.staff_change(order, Order.Status.NEEDS_INFO)
        with self.assertRaises(ValidationError):
            self.staff_change(order, Order.Status.IN_PROGRESS)
        order = self.staff_change(order, Order.Status.IN_PROGRESS, assigned_to=self.admin)
        order = self.staff_change(order, Order.Status.READY)
        order = self.staff_change(order, Order.Status.COMPLETED)
        self.assertFalse(order.can_edit)

    def test_customer_cannot_set_owner_status_or_executor(self):
        response = self.client.post(reverse("orders:create"),
            self.data(owner=self.other.pk, status="ready", assigned_to=self.admin.pk))
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.owner, self.owner)
        self.assertEqual(order.status, Order.Status.SUBMITTED)
        self.assertIsNone(order.assigned_to)

    def test_only_own_orders_and_files_are_accessible(self):
        order = self.create([self.pdf()])
        attachment = order.files.get()
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("orders:list")), order.title)
        for name in ["detail", "edit", "cancel"]:
            url = reverse("orders:" + name, args=[order.pk])
            self.assertEqual(self.client.post(url, self.data()).status_code,
                             405 if name == "detail" else 404)
            if name != "cancel":
                self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(reverse("orders:download", args=[attachment.pk])).status_code, 404)

    def test_download_attachment_headers_and_staff_access(self):
        attachment = self.create([self.pdf()]).files.get()
        for user in [self.owner, self.admin]:
            self.client.force_login(user)
            response = self.client.get(reverse("orders:download", args=[attachment.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment;", response["Content-Disposition"])
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))

    def test_cancel_only_before_processing(self):
        order = self.create()
        url = reverse("orders:cancel", args=[order.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        other = self.staff_change(self.create(), Order.Status.REVIEWING)
        self.assertEqual(self.client.post(reverse("orders:cancel", args=[other.pk])).status_code, 409)

    def test_anonymous_redirect_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get(reverse("orders:create")).status_code, 302)
        client.force_login(self.owner)
        self.assertEqual(client.post(reverse("orders:create"), self.data()).status_code, 403)

    def test_admin_card_renders_and_does_not_change_status_on_get(self):
        order = self.create([self.pdf()])
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:orders_order_change", args=[order.pk]))
        self.assertContains(response, "Принят в обработку")
        self.assertContains(response, "task.pdf")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SUBMITTED)

    def admin_data(self, order, **changes):
        data = {"status": "reviewing", "assigned_to": "", "feedback": "", "revision": order.revision,
                "files-TOTAL_FORMS": "0", "files-INITIAL_FORMS": "0",
                "history-TOTAL_FORMS": "0", "history-INITIAL_FORMS": "0", "_save": "Сохранить"}
        data.update(changes)
        return data

    def test_admin_processing_and_stale_form(self):
        order = self.create()
        self.client.force_login(self.admin)
        url = reverse("admin:orders_order_change", args=[order.pk])
        response = self.client.post(url, self.admin_data(order))
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.REVIEWING)
        self.assertEqual(order.history.count(), 2)
        response = self.client.post(url, self.admin_data(order, revision=1))
        self.assertContains(response, "Заказ изменился")
