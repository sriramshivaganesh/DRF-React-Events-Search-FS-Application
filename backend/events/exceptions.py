from django.db import DatabaseError
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Uniform error body: {"detail": str, "errors": {field: [messages]}?}."""
    if isinstance(exc, DatabaseError):
        return Response(
            {"detail": "The database is unavailable or busy; please retry."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    response = exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, ValidationError):
        errors = exc.detail
        if isinstance(errors, list):
            errors = {"non_field_errors": errors}
        response.data = {"detail": "Validation failed.", "errors": errors}
    elif isinstance(response.data, dict) and "detail" in response.data:
        response.data = {"detail": str(response.data["detail"])}
    return response
