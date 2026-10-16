"""Importing an archive into the database (no search logic here).

Design:
* One SHA-256 per archive identifies a re-upload (documented in the README).
* The whole import runs in a single transaction: a failure rolls everything
  back, so the table never contains a half-imported archive.
* Files are streamed line by line and rows are inserted in batches.
* `serialno` is unique. Rows whose serial already exists (earlier in this
  archive or from a previous upload) are counted as duplicates and skipped, so
  overlapping archives never create duplicate events.
"""
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from ..models import Event, Ingestion
from .archive_service import ARCHIVE_READ_ERRORS, ArchiveError, open_archive_entries, validate_archive
from .parser_service import iter_parsed_lines

log = logging.getLogger(__name__)
MAX_RECORDED_ERRORS = 50


class IngestionFailed(Exception):
    pass


@dataclass
class _Stats:
    files_processed: int = 0
    files_skipped: int = 0
    records_read: int = 0
    records_imported: int = 0
    records_duplicate: int = 0
    records_invalid: int = 0
    errors: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        if len(self.errors) < MAX_RECORDED_ERRORS:
            self.errors.append(message)


def start_ingestion(sha256: str, original_name: str, size: int) -> tuple[Ingestion, bool]:
    """Return (ingestion, should_run). should_run is False for an already-seen archive."""
    with transaction.atomic():
        ingestion, created = Ingestion.objects.get_or_create(
            archive_sha256=sha256,
            defaults={"original_name": original_name[:255], "size_bytes": size},
        )
        if created:
            return ingestion, True
        if ingestion.status == Ingestion.Status.FAILED:
            # A failed attempt rolled back all rows, so retrying the same bytes is safe.
            Ingestion.objects.filter(pk=ingestion.pk).update(
                status=Ingestion.Status.RUNNING, original_name=original_name[:255], errors=[], finished_at=None
            )
            ingestion.refresh_from_db()
            return ingestion, True
        return ingestion, False  # completed (duplicate) or running (in progress)


def run_ingestion(ingestion: Ingestion, archive_path: Path) -> Ingestion:
    stats = _Stats()
    try:
        validate_archive(archive_path)
        with transaction.atomic():
            with open_archive_entries(archive_path) as entries:
                for entry in entries:
                    if entry.fileobj is None:
                        stats.files_skipped += 1
                        stats.note(f"Skipped {entry.name}: {entry.skip_reason}")
                        continue
                    _ingest_file(entry.name, entry.fileobj, stats)
            if stats.records_imported + stats.records_duplicate == 0:
                raise IngestionFailed("No valid event records were found in the archive.")
    except IngestionFailed as exc:
        return _finish(ingestion, stats, Ingestion.Status.FAILED, str(exc))
    except ArchiveError as exc:
        return _finish(ingestion, stats, Ingestion.Status.FAILED, str(exc), invalid_archive=True)
    except ARCHIVE_READ_ERRORS as exc:
        return _finish(
            ingestion, stats, Ingestion.Status.FAILED, f"Archive is corrupt or truncated: {exc}", invalid_archive=True
        )
    except Exception:
        log.exception("Unexpected ingestion failure")
        _finish(ingestion, stats, Ingestion.Status.FAILED, "Unexpected error while importing; nothing was imported.")
        raise
    ingestion = _finish(ingestion, stats, Ingestion.Status.COMPLETED)
    _refresh_planner_statistics()
    return ingestion


def _finish(
    ingestion: Ingestion, stats: _Stats, status: str, error: str | None = None, invalid_archive: bool = False
) -> Ingestion:
    failed = status == Ingestion.Status.FAILED
    if failed:
        # The transaction was rolled back, so nothing from this run was stored.
        stats.records_imported = 0
        stats.records_duplicate = 0
        stats.errors.insert(0, error or "Ingestion failed.")
    ingestion.invalid_archive = invalid_archive  # transient, lets the view choose 400 vs 422
    ingestion.status = status
    ingestion.files_processed = stats.files_processed
    ingestion.files_skipped = stats.files_skipped
    ingestion.records_read = stats.records_read
    ingestion.records_imported = stats.records_imported
    ingestion.records_duplicate = stats.records_duplicate
    ingestion.records_invalid = stats.records_invalid
    ingestion.errors = stats.errors[: MAX_RECORDED_ERRORS + 1]
    ingestion.finished_at = timezone.now()
    ingestion.save()
    return ingestion


def _ingest_file(name: str, fileobj, stats: _Stats) -> None:
    stats.files_processed += 1
    batch: dict[str, Event] = {}
    text = io.TextIOWrapper(fileobj, encoding="utf-8", errors="replace")
    for parsed in iter_parsed_lines(text):
        stats.records_read += 1
        if parsed.error:
            stats.records_invalid += 1
            stats.note(f"{name}:{parsed.line_no}: {parsed.error}")
            continue
        serial = parsed.values["serialno"]
        if serial in batch:
            stats.records_duplicate += 1
            continue
        batch[serial] = Event(source_file=name, **parsed.values)
        if len(batch) >= settings.INGEST_BATCH_SIZE:
            _flush(batch, stats)
            batch = {}
    if batch:
        _flush(batch, stats)
    text.detach()  # leave closing to the tar reader


def _flush(batch: dict[str, Event], stats: _Stats) -> None:
    existing = set(Event.objects.filter(serialno__in=list(batch)).values_list("serialno", flat=True))
    new_rows = [event for serial, event in batch.items() if serial not in existing]
    Event.objects.bulk_create(new_rows, batch_size=settings.INGEST_BATCH_SIZE)
    stats.records_imported += len(new_rows)
    stats.records_duplicate += len(batch) - len(new_rows)


def _refresh_planner_statistics() -> None:
    """Give SQLite's planner row statistics so it picks the most selective index."""
    with connection.cursor() as cursor:
        cursor.execute("ANALYZE")
