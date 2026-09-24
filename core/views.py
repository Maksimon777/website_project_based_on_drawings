import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@require_safe
def home(request):
    return render(request, "core/home.html")


@require_safe
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError as error:
        # Only the error type is logged: connection details may contain secrets.
        logger.error("Database health check failed (%s)", type(error).__name__)
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})
