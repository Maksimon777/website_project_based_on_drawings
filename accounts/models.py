from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Project-owned user model, extensible before adding registration."""
