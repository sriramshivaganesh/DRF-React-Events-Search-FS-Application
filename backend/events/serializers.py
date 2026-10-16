from rest_framework import serializers

from .fields import EVENT_FIELDS, FILE_KEY
from .models import Ingestion


def event_to_api(row: dict) -> dict:
    """Map a DB row (model attribute names) to the external API field names.

    Plain dict mapping instead of a DRF Serializer: it is the hot path for up to
    200 rows per request and needs no validation machinery.
    """
    out = {spec.api_name: row[spec.attr] for spec in EVENT_FIELDS}
    out[FILE_KEY] = row["source_file"]
    return out


class IngestionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Ingestion
        fields = [
            "id", "original_name", "archive_sha256", "size_bytes", "status",
            "files_processed", "files_skipped", "records_read", "records_imported",
            "records_duplicate", "records_invalid", "errors", "created_at", "finished_at",
        ]
