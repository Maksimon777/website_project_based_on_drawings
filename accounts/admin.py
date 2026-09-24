from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class ProjectUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Получение результата", {"fields": ("telegram", "delivery_method")}),
    )
