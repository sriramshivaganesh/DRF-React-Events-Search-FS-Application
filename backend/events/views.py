import logging

from django.conf import settings
from django.db import connection
from django.db.models import Count
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Event, Ingestion
from .serializers import IngestionSerializer, event_to_api
from .services import archive_service, ingestion_service, search_service

log = logging.getLogger(__name__)


class HealthView(APIView):
    """Readiness: succeeds only if the database answers."""

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            log.exception("health check failed")
            return Response({"status": "unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok"})


class EventSearchView(APIView):
    def get(self, request):
        search = search_service.parse_search_request(request.query_params)
        outcome = search_service.search_events(search)
        return Response(
            {
                "count": outcome.count,
                "page": search.page,
                "page_size": search.page_size,
                "total_pages": outcome.total_pages,
                "search_time_ms": round(outcome.elapsed_seconds * 1000, 3),
                "search_time_seconds": round(outcome.elapsed_seconds, 6),
                "results": [event_to_api(row) for row in outcome.rows],
            }
        )


class ArchiveUploadView(APIView):
    """POST multipart/form-data with a `file` part containing a .tgz archive.

    201 = imported, 200 = identical archive already imported (nothing re-imported),
    400 = invalid archive, 409 = same archive currently importing,
    413 = too large, 422 = archive readable but could not be imported.
    """

    parser_classes = [MultiPartParser]

    def post(self, request):
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": ["A .tgz archive must be sent in the 'file' form field."]})
        if not archive_service.has_supported_extension(uploaded.name):
            raise ValidationError({"file": ["Only .tgz or .tar.gz archives are supported."]})

        try:
            path, sha256, size = archive_service.store_upload(uploaded)
        except archive_service.UploadTooLarge as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        except archive_service.ArchiveError as exc:
            raise ValidationError({"file": [str(exc)]}) from exc

        ingestion, should_run = ingestion_service.start_ingestion(sha256, uploaded.name, size)
        if not should_run:
            if ingestion.status == Ingestion.Status.RUNNING:
                return Response(
                    {"detail": "This archive is currently being imported.", "ingestion": IngestionSerializer(ingestion).data},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(
                {"detail": "This archive was already imported; nothing was re-imported.", "duplicate": True,
                 "ingestion": IngestionSerializer(ingestion).data},
                status=status.HTTP_200_OK,
            )

        ingestion = ingestion_service.run_ingestion(ingestion, path)
        data = IngestionSerializer(ingestion).data
        if ingestion.status == Ingestion.Status.FAILED:
            reason = ingestion.errors[0] if ingestion.errors else "Ingestion failed."
            # Unreadable/unsafe archive = client error; readable but empty of events = 422.
            code = status.HTTP_400_BAD_REQUEST if ingestion.invalid_archive else status.HTTP_422_UNPROCESSABLE_ENTITY
            return Response({"detail": reason, "duplicate": False, "ingestion": data}, status=code)
        return Response({"detail": "Archive imported.", "duplicate": False, "ingestion": data}, status=status.HTTP_201_CREATED)


class IngestionListView(APIView):
    def get(self, request):
        return Response(IngestionSerializer(Ingestion.objects.all()[:50], many=True).data)


class IngestionDetailView(APIView):
    def get(self, request, pk: int):
        try:
            ingestion = Ingestion.objects.get(pk=pk)
        except Ingestion.DoesNotExist:
            raise NotFound("Ingestion not found.") from None
        return Response(IngestionSerializer(ingestion).data)


class SummaryView(APIView):
    """Dataset summary: total events, distinct source files and the latest ingestion."""

    def get(self, request):
        total = Event.objects.count()
        files = Event.objects.values("source_file").distinct().count() if total else 0
        latest = Ingestion.objects.filter(status=Ingestion.Status.COMPLETED).first()
        return Response(
            {
                "total_events": total,
                "source_files": files,
                "completed_ingestions": Ingestion.objects.filter(status=Ingestion.Status.COMPLETED).count(),
                "latest_ingestion": IngestionSerializer(latest).data if latest else None,
                "max_upload_bytes": settings.MAX_UPLOAD_BYTES,
            }
        )
