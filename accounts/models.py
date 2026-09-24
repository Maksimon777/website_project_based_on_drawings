from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

TELEGRAM_PATTERN = r"^@[A-Za-z][A-Za-z0-9_]{4,31}$"


class User(AbstractUser):
    class DeliveryMethod(models.TextChoices):
        EMAIL = "email", "Email"
        TELEGRAM = "telegram", "Telegram"

    telegram = models.CharField(
        "Telegram", max_length=33, blank=True,
        validators=[RegexValidator(TELEGRAM_PATTERN, "Введите @username: 5–32 латинских символа, цифры или _, начиная с буквы.")],
    )
    delivery_method = models.CharField(
        "Способ получения результата", max_length=8,
        choices=DeliveryMethod.choices, default=DeliveryMethod.EMAIL,
    )

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"), condition=~models.Q(email=""),
                name="accounts_unique_email_ci",
            )
        ]
