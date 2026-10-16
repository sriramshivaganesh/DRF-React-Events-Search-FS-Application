"""CLI equivalent of the upload endpoint: `manage.py import_archive path/to/events.tgz`."""
import hashlib
import shutil
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from events.services import archive_service, ingestion_service


class Command(BaseCommand):
    help = "Import a .tgz event archive (same pipeline as the upload API)."

    def add_arguments(self, parser):
        parser.add_argument("archive", type=Path)

    def handle(self, *args, archive: Path, **options):
        if not archive.is_file() or not archive_service.has_supported_extension(archive.name):
            raise CommandError("Provide an existing .tgz / .tar.gz file.")
        sha = hashlib.sha256()
        with archive.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                sha.update(chunk)
        stored = Path(settings.UPLOAD_DIR) / f"{sha.hexdigest()}.tgz"
        if not stored.exists():
            shutil.copyfile(archive, stored)
        ingestion, should_run = ingestion_service.start_ingestion(sha.hexdigest(), archive.name, archive.stat().st_size)
        if not should_run:
            self.stdout.write(f"Archive already {ingestion.status}; nothing imported.")
            return
        started = time.perf_counter()
        ingestion = ingestion_service.run_ingestion(ingestion, stored)
        elapsed = time.perf_counter() - started
        self.stdout.write(
            f"{ingestion.status}: files={ingestion.files_processed} skipped_files={ingestion.files_skipped} "
            f"read={ingestion.records_read} imported={ingestion.records_imported} "
            f"duplicates={ingestion.records_duplicate} invalid={ingestion.records_invalid} ({elapsed:.2f}s)"
        )
        if ingestion.status == "failed":
            raise CommandError(ingestion.errors[0] if ingestion.errors else "ingestion failed")
