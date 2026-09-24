import logging

from django.db import DatabaseError
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class AccountDatabaseErrorMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        if request.path.startswith("/accounts/") and isinstance(exception, DatabaseError):
            logger.error("Account operation failed (%s)", type(exception).__name__)
            # A standalone response avoids querying the unavailable session database again.
            response = HttpResponse(
                render_to_string("accounts/unavailable.html"), status=503,
            )
            response["Cache-Control"] = "no-store"
            return response
        return None
