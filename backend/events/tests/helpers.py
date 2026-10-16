import io
import tarfile
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

SAMPLE = "1 2 348935949 eni-293216456 159.62.125.136 30.55.177.194 152 23475 8 10 3929334 1725850449 1725855086 REJECT OK"


def line(serial, **over):
    """Build one log line; keyword names are model attribute names (e.g. account_id)."""
    base = dict(
        serialno=str(serial), version="2", account_id="348935949", instance_id="eni-293216456",
        srcaddr="159.62.125.136", dstaddr="30.55.177.194", srcport="152", dstport="23475", protocol="8",
        packets="10", bytes="3929334", starttime="1725850449", endtime="1725855086", action="REJECT", log_status="OK",
    )
    base.update({k: str(v) for k, v in over.items()})
    return " ".join(base.values())


def make_tgz(files: dict, extra=None) -> bytes:
    """In-memory .tgz. `extra` is a callable receiving the TarFile for crafted members."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if extra:
            extra(tar)
    return buf.getvalue()


def upload_file(data: bytes, name="events.tgz"):
    return SimpleUploadedFile(name, data, content_type="application/gzip")


class TempUploadDirMixin:
    """Redirect stored archives to a throw-away directory."""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        override = override_settings(UPLOAD_DIR=Path(self._tmp.name))
        override.enable()
        self.addCleanup(override.disable)
