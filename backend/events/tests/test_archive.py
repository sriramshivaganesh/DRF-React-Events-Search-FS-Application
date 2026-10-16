import tarfile
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from ..services import archive_service as a
from .helpers import line, make_tgz


class ArchiveSafetyTests(SimpleTestCase):
    def _write(self, data):
        tmp = tempfile.NamedTemporaryFile(suffix=".tgz", delete=False)
        tmp.write(data)
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        return Path(tmp.name)

    def test_member_name_checks(self):
        self.assertEqual(a.check_member_name("events/xaa"), "events/xaa")
        for bad in ["/etc/passwd", "../evil", "a/../../evil", "C:/x", "a\\b", ""]:
            with self.subTest(bad=bad), self.assertRaises(a.ArchiveError):
                a.check_member_name(bad)

    def test_path_traversal_member_rejected(self):
        path = self._write(make_tgz({"../evil": line(1)}))
        with self.assertRaises(a.ArchiveError):
            a.validate_archive(path)

    def test_symlink_member_rejected(self):
        def add_link(tar):
            info = tarfile.TarInfo("link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)

        path = self._write(make_tgz({"ok": line(1)}, extra=add_link))
        with self.assertRaisesMessage(a.ArchiveError, "Links are not allowed"):
            a.validate_archive(path)

    @override_settings(MAX_EXTRACTED_BYTES=10)
    def test_oversized_expansion_rejected(self):
        path = self._write(make_tgz({"big": "x" * 100}))
        with self.assertRaises(a.ArchiveError):
            a.validate_archive(path)

    def test_entries_skip_hidden_empty_binary(self):
        path = self._write(make_tgz({"d/xaa": line(1), "d/._xaa": "junk", "d/empty": "", "d/bin": b"\x00\x01\x02"}))
        with a.open_archive_entries(path) as entries:
            result = {e.name: e.skip_reason for e in entries}
        self.assertIsNone(result["xaa"])
        self.assertEqual(result["d/._xaa"], "hidden/metadata file")
        self.assertEqual(result["empty"], "empty file")
        self.assertEqual(result["bin"], "binary file")

    def test_supported_extensions(self):
        self.assertTrue(a.has_supported_extension("Events.TGZ"))
        self.assertTrue(a.has_supported_extension("e.tar.gz"))
        self.assertFalse(a.has_supported_extension("e.zip"))
