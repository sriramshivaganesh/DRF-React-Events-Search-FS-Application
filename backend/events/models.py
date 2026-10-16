from django.db import models


class Ingestion(models.Model):
    """One uploaded archive and the outcome of importing it."""

    class Status(models.TextChoices):
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"

    # SHA-256 of the archive bytes: re-uploading identical bytes is detected via this unique key.
    archive_sha256 = models.CharField(max_length=64, unique=True)
    original_name = models.CharField(max_length=255)
    size_bytes = models.BigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    files_processed = models.IntegerField(default=0)
    files_skipped = models.IntegerField(default=0)
    records_read = models.IntegerField(default=0)
    records_imported = models.IntegerField(default=0)
    records_duplicate = models.IntegerField(default=0)
    records_invalid = models.IntegerField(default=0)
    errors = models.JSONField(default=list)  # capped list of human-readable messages
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-id"]


class Event(models.Model):
    # Identifiers are strings so leading zeros etc. are never lost.
    serialno = models.CharField(max_length=32, unique=True)  # event identity; the unique index doubles as lookup index
    version = models.CharField(max_length=16, null=True)
    account_id = models.CharField(max_length=32, null=True)
    instance_id = models.CharField(max_length=64, null=True)
    srcaddr = models.CharField(max_length=45, null=True)  # 45 = longest textual IPv6
    dstaddr = models.CharField(max_length=45, null=True)
    srcport = models.IntegerField(null=True)
    dstport = models.IntegerField(null=True)
    protocol = models.IntegerField(null=True)
    packets = models.BigIntegerField(null=True)
    bytes = models.BigIntegerField(null=True)
    starttime = models.BigIntegerField(null=True)
    endtime = models.BigIntegerField(null=True)
    # Stored upper-cased at ingest so case-insensitive search is a plain indexable equality.
    action = models.CharField(max_length=16, null=True)
    log_status = models.CharField(max_length=16, null=True)
    source_file = models.CharField(max_length=255)

    class Meta:
        # Chosen from the observed data (see README): high-cardinality columns get
        # single-column indexes; the low-cardinality ones (version ~6 values, protocol 11,
        # action 2, log_status 2) are only useful together, so they share one composite index.
        indexes = [
            models.Index(fields=["account_id"], name="ev_account_idx"),
            models.Index(fields=["instance_id"], name="ev_instance_idx"),
            models.Index(fields=["srcaddr"], name="ev_srcaddr_idx"),
            models.Index(fields=["dstaddr"], name="ev_dstaddr_idx"),
            models.Index(fields=["srcport"], name="ev_srcport_idx"),
            models.Index(fields=["dstport"], name="ev_dstport_idx"),
            models.Index(fields=["packets"], name="ev_packets_idx"),
            models.Index(fields=["bytes"], name="ev_bytes_idx"),
            models.Index(fields=["starttime"], name="ev_start_idx"),
            models.Index(fields=["endtime"], name="ev_end_idx"),
            models.Index(fields=["action", "log_status", "protocol", "version"], name="ev_lowcard_idx"),
        ]
