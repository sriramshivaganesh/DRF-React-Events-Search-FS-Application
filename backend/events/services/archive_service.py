"""Upload storage and safe reading of .tgz archives.

Security model: archive members are never written to disk under their own names.
Each regular file is streamed straight from the tar into the parser, so path
traversal / absolute paths / symlink tricks cannot touch the filesystem. Member
names are still validated up front and any archive containing an unsafe member
is rejected outright rather than partially processed.
"""
import hashlib
import os
import tarfile
import tempfile
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO

from django.conf import settings

SUPPORTED_SUFFIXES = (".tgz", ".tar.gz")
GZIP_MAGIC = b"\x1f\x8b"
ARCHIVE_READ_ERRORS = (tarfile.TarError, EOFError, zlib.error, OSError)


class ArchiveError(Exception):
    """The upload is not a usable archive (reported to the client as HTTP 400)."""


class UploadTooLarge(ArchiveError):
    pass


@dataclass
class ArchiveEntry:
    name: str  # base filename, stored as the event's source file
    fileobj: IO[bytes] | None  # None when the entry is skipped
    skip_reason: str | None = None


def has_supported_extension(filename: str) -> bool:
    return filename.lower().endswith(SUPPORTED_SUFFIXES)


def store_upload(uploaded, max_bytes: int | None = None) -> tuple[Path, str, int]:
    """Stream an uploaded file into UPLOAD_DIR, hashing as we go.

    Returns (final_path, sha256_hex, size). The file is named after its hash, so
    identical uploads map to the same path. Enforces the size limit while
    streaming (the Content-Length header alone is not trusted).
    """
    max_bytes = settings.MAX_UPLOAD_BYTES if max_bytes is None else max_bytes
    digest = hashlib.sha256()
    size = 0
    # The directory is created at startup, but may have been removed since (e.g. data folder deleted).
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=settings.UPLOAD_DIR, prefix=".upload-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out:
            for chunk in uploaded.chunks():
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLarge(f"Archive exceeds the {max_bytes} byte upload limit.")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise ArchiveError("The uploaded file is empty.")
        with open(tmp_name, "rb") as check:
            if check.read(2) != GZIP_MAGIC:
                raise ArchiveError("The file is not a gzip-compressed tar archive.")
        sha = digest.hexdigest()
        final = Path(settings.UPLOAD_DIR) / f"{sha}.tgz"
        os.replace(tmp_name, final)
        return final, sha, size
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def check_member_name(name: str) -> str:
    """Return the safe relative POSIX path of `name` or raise ArchiveError."""
    if not name or "\x00" in name or "\\" in name:
        raise ArchiveError(f"Unsafe member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or (len(name) > 1 and name[1] == ":"):
        raise ArchiveError(f"Absolute path in archive: {name!r}")
    if ".." in path.parts:
        raise ArchiveError(f"Path traversal in archive: {name!r}")
    return str(path)


def _open_tar(path: Path) -> tarfile.TarFile:
    try:
        return tarfile.open(path, mode="r:gz")
    except ARCHIVE_READ_ERRORS as exc:
        raise ArchiveError(f"Cannot read archive: {exc}") from exc


def validate_archive(path: Path) -> int:
    """Walk the archive headers once; reject unsafe/oversized archives. Returns member count."""
    total = 0
    count = 0
    try:
        with _open_tar(path) as tar:
            for member in tar:
                count += 1
                if count > settings.MAX_ARCHIVE_MEMBERS:
                    raise ArchiveError("Archive contains too many entries.")
                check_member_name(member.name)
                if member.issym() or member.islnk():
                    raise ArchiveError(f"Links are not allowed in archives: {member.name!r}")
                if member.isdev() or member.isfifo():
                    raise ArchiveError(f"Special files are not allowed in archives: {member.name!r}")
                if member.isfile():
                    total += member.size
                    if total > settings.MAX_EXTRACTED_BYTES:
                        raise ArchiveError("Archive expands beyond the allowed size.")
            # tarfile stops at the end-of-archive marker; drain the gzip stream so a
            # truncated trailer / CRC mismatch is detected here rather than silently accepted.
            while tar.fileobj.read(1024 * 1024):
                pass
    except ArchiveError:
        raise
    except ARCHIVE_READ_ERRORS as exc:
        raise ArchiveError(f"Archive is corrupt or truncated: {exc}") from exc
    return count


@contextmanager
def open_archive_entries(path: Path) -> Iterator[Iterator[ArchiveEntry]]:
    """Context manager yielding an iterator of ArchiveEntry for regular files.

    Directories are ignored; hidden files (e.g. macOS `._*`), empty files and
    binary files are yielded with a skip_reason instead of a file object.
    """
    tar = _open_tar(path)

    def generate() -> Iterator[ArchiveEntry]:
        for member in tar:
            if not member.isfile():
                continue
            rel = check_member_name(member.name)
            base = PurePosixPath(rel).name
            if base.startswith("."):
                yield ArchiveEntry(rel, None, "hidden/metadata file")
            elif member.size == 0:
                yield ArchiveEntry(base, None, "empty file")
            elif len(base) > 255:
                yield ArchiveEntry(base[:60] + "...", None, "file name too long")
            else:
                fileobj = tar.extractfile(member)
                if fileobj is None:
                    yield ArchiveEntry(base, None, "unreadable entry")
                    continue
                head = fileobj.read(4096)
                if b"\x00" in head:
                    yield ArchiveEntry(base, None, "binary file")
                    continue
                fileobj.seek(0)
                yield ArchiveEntry(base, fileobj)

    try:
        yield generate()
    finally:
        tar.close()
