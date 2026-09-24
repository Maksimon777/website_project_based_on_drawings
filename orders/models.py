from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import models


def source_file_path(instance, filename):
    return f"orders/{instance.order_id}/{uuid4().hex}{Path(filename).suffix.lower()}"


class Order(models.Model):
    class Category(models.TextChoices):
        GEOMETRY = "geometry", "Начертательная геометрия"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Отправлен"
        REVIEWING = "reviewing", "Принят в обработку"
        NEEDS_INFO = "needs_info", "Нужно уточнение"
        IN_PROGRESS = "in_progress", "На выполнении"
        READY = "ready", "Готов"
        COMPLETED = "completed", "Завершён"
        CANCELLED = "cancelled", "Отменён"

    OUTPUT_FORMATS = [
        ("pdf", "PDF"), ("kompas", "Файл КОМПАС"), ("dwg_dxf", "DWG / DXF"),
        ("image", "Изображение"), ("print", "Подготовить к печати"),
        ("hand", "Работа от руки"), ("other", "Другое"),
    ]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders", verbose_name="Клиент")
    title = models.CharField("Название", max_length=200)
    category = models.CharField("Категория", max_length=16, choices=Category.choices)
    description = models.TextField("Описание задания")
    teacher_requirements = models.TextField("Требования преподавателя", blank=True)
    deadline = models.DateField("Желаемый срок")
    output_formats = models.JSONField("Форматы результата", default=list)
    other_format = models.CharField("Другой формат результата", max_length=200, blank=True)
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.SUBMITTED)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_orders", verbose_name="Исполнитель", limit_choices_to={"is_staff": True, "is_active": True})
    feedback = models.TextField("Что нужно уточнить (видно клиенту)", blank=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "заказ"
        verbose_name_plural = "заказы"
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    @property
    def can_edit(self):
        return self.status in (self.Status.SUBMITTED, self.Status.NEEDS_INFO)

    @property
    def output_labels(self):
        labels = dict(self.OUTPUT_FORMATS)
        return ", ".join(labels.get(value, value) for value in self.output_formats)

    def __str__(self):
        return f"№{self.pk} — {self.title}"


class OrderFile(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="files")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    file = models.FileField(upload_to=source_file_path, max_length=300)
    original_name = models.CharField("Имя файла", max_length=255)
    size = models.PositiveBigIntegerField("Размер")
    created_at = models.DateTimeField("Загружен", auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "исходный файл"
        verbose_name_plural = "исходные файлы"

    def __str__(self):
        return self.original_name


class StatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    old_status = models.CharField("Было", max_length=16, choices=Order.Status.choices, blank=True)
    new_status = models.CharField("Стало", max_length=16, choices=Order.Status.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    note = models.TextField("Комментарий", blank=True)
    created_at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "изменение статуса"
        verbose_name_plural = "история статусов"
