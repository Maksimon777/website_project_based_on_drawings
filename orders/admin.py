from django import forms
from django.contrib import admin
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html

from accounts.models import User
from .models import Order, OrderFile, StatusHistory
from .services import update_by_staff, validate_transition


class ProcessingForm(forms.ModelForm):
    revision = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = Order
        fields = ("status", "assigned_to", "feedback", "revision")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(is_staff=True, is_active=True)

    def clean(self):
        data = super().clean()
        if self.instance.pk and not self.errors:
            original = Order.objects.get(pk=self.instance.pk)
            if data["revision"] != original.revision:
                raise forms.ValidationError("Заказ изменился. Обновите страницу, прежде чем сохранять.")
            validate_transition(original, data["status"], data.get("assigned_to"), data.get("feedback", ""))
        return data


class FileInline(admin.TabularInline):
    model = OrderFile
    fields = ("download_link", "size", "uploaded_by", "created_at")
    readonly_fields = fields
    extra = 0
    can_delete = False

    @admin.display(description="Скачать исходный файл")
    def download_link(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("orders:download", args=[obj.pk]), obj.original_name)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class HistoryInline(admin.TabularInline):
    model = StatusHistory
    fields = ("old_status", "new_status", "changed_by", "note", "created_at")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = ProcessingForm
    list_display = ("id", "title", "owner", "status", "assigned_to", "deadline", "created_at")
    list_filter = ("status", "category", "assigned_to")
    search_fields = ("=id", "title", "owner__email")
    list_select_related = ("owner", "assigned_to")
    readonly_fields = ("owner", "customer_contacts", "title", "category", "description",
                       "teacher_requirements", "deadline", "output_labels",
                       "other_format", "created_at", "updated_at", "processing_help")
    fields = readonly_fields + ("status", "assigned_to", "feedback", "revision")
    inlines = (FileInline, HistoryInline)

    @admin.display(description="Обработка")
    def processing_help(self, obj):
        return "Чтобы заблокировать редактирование клиентом, выберите «Принят в обработку» и сохраните. Простое открытие карточки статус не меняет."

    @admin.display(description="Контакты клиента")
    def customer_contacts(self, obj):
        return f"{obj.owner.first_name}; email: {obj.owner.email}; Telegram: {obj.owner.telegram or 'не указан'}; способ: {obj.owner.get_delivery_method_display()}"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if request.method == "POST" and object_id:
            # Hold the same row lock during validation and saving to prevent stale
            # admin forms from overwriting client edits or another administrator.
            with transaction.atomic():
                if str(object_id).isdigit():
                    Order.objects.select_for_update().filter(pk=object_id).first()
                return super().changeform_view(request, object_id, form_url, extra_context)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        saved = update_by_staff(
            actor=request.user, order_id=obj.pk, status=form.cleaned_data["status"],
            assigned_to=form.cleaned_data["assigned_to"], feedback=form.cleaned_data["feedback"],
            revision=form.cleaned_data["revision"],
        )
        obj.revision, obj.updated_at = saved.revision, saved.updated_at
