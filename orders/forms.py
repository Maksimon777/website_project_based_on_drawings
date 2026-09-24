from django import forms
from django.utils import timezone

from .models import Order
from .validators import ALLOWED_EXTENSIONS, validate_source_file

REQUIRED_MESSAGE = "Это поле обязательное."


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        values = data if isinstance(data, (list, tuple)) else [data]
        result = []
        for value in values:
            upload = super().clean(value, initial)
            validate_source_file(upload)
            result.append(upload)
        return result


class OrderForm(forms.ModelForm):
    revision = forms.IntegerField(widget=forms.HiddenInput, required=False)
    output_formats = forms.MultipleChoiceField(
        label="Форматы результата", choices=Order.OUTPUT_FORMATS,
        widget=forms.CheckboxSelectMultiple,
    )
    files = MultipleFileField(
        label="Исходные файлы", required=False, max_length=255,
        widget=MultipleFileInput(attrs={"accept": ",".join(sorted(ALLOWED_EXTENSIONS))}),
        help_text="Можно выбрать несколько файлов. После ошибки формы выберите их повторно.",
    )

    class Meta:
        model = Order
        fields = ("title", "category", "description", "teacher_requirements",
                  "deadline", "output_formats", "other_format")
        widgets = {
            "deadline": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={"rows": 7}),
            "teacher_requirements": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["revision"] = self.instance.revision
        self.fields["deadline"].widget.attrs["min"] = timezone.localdate().isoformat()
        for field in self.fields.values():
            field.error_messages["required"] = REQUIRED_MESSAGE

    def clean_deadline(self):
        deadline = self.cleaned_data["deadline"]
        if deadline < timezone.localdate():
            raise forms.ValidationError("Срок не может быть в прошлом.")
        return deadline

    def clean(self):
        data = super().clean()
        if "other" in data.get("output_formats", []) and not data.get("other_format"):
            self.add_error("other_format", "Укажите, какой другой формат нужен.")
        elif "other" not in data.get("output_formats", []):
            data["other_format"] = ""
        return data
