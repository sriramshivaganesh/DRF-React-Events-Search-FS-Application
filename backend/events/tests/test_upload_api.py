from unittest import mock

from django.test import override_settings
from rest_framework.test import APITestCase

from ..models import Event, Ingestion
from .helpers import TempUploadDirMixin, line, make_tgz, upload_file

URL = "/api/v1/uploads/"


class UploadApiTests(TempUploadDirMixin, APITestCase):
    def post(self, data: bytes, name="events.tgz"):
        return self.client.post(URL, {"file": upload_file(data, name)}, format="multipart")

    def test_valid_archive_imported_and_filenames_preserved(self):
        data = make_tgz({"events/events_2025.log": f"{line(1)}\n{line(2)}\n", "events/other.log": line(3) + "\n"})
        response = self.post(data)
        self.assertEqual(response.status_code, 201, response.data)
        summary = response.data["ingestion"]
        self.assertEqual(
            (summary["status"], summary["files_processed"], summary["records_imported"]), ("completed", 2, 3)
        )
        self.assertEqual(Event.objects.get(serialno="2").source_file, "events_2025.log")
        self.assertEqual(Event.objects.get(serialno="3").source_file, "other.log")

    def test_invalid_and_duplicate_records_are_reported(self):
        data = make_tgz({"a.log": f"{line(1)}\nbad line\n{line(1)}\n", "b.log": line(1) + "\n" + line(2) + "\n"})
        summary = self.post(data).data["ingestion"]
        self.assertEqual(summary["records_read"], 5)
        self.assertEqual(summary["records_imported"], 2)
        self.assertEqual(summary["records_duplicate"], 2)
        self.assertEqual(summary["records_invalid"], 1)
        self.assertTrue(any("a.log:2" in e for e in summary["errors"]))
        self.assertEqual(Event.objects.get(serialno="1").source_file, "a.log")  # first occurrence wins

    def test_same_archive_twice_is_not_reimported(self):
        data = make_tgz({"a.log": line(1)})
        self.assertEqual(self.post(data).status_code, 201)
        second = self.post(data, name="renamed.tgz")
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["duplicate"])
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Ingestion.objects.count(), 1)

    def test_overlapping_archive_skips_existing_serials(self):
        self.post(make_tgz({"a.log": line(1) + "\n" + line(2)}))
        summary = self.post(make_tgz({"b.log": line(2) + "\n" + line(3)})).data["ingestion"]
        self.assertEqual((summary["records_imported"], summary["records_duplicate"]), (1, 1))
        self.assertEqual(Event.objects.count(), 3)

    def test_rejections(self):
        cases = {
            "wrong extension": (self.post(b"x", "events.zip"), 400),
            "not gzip": (self.post(b"plain text data", "events.tgz"), 400),
            "empty": (self.post(b"", "events.tgz"), 400),
            "corrupt": (self.post(make_tgz({"a.log": line(1)})[:-20], "events.tgz"), 400),
            "traversal": (self.post(make_tgz({"../x.log": line(1)})), 400),
            "no events": (self.post(make_tgz({"a.log": "nothing useful\n"})), 422),
            "only unsupported": (self.post(make_tgz({"._a": "x", "b": b"\x00\x00"})), 422),
        }
        for label, (response, expected) in cases.items():
            with self.subTest(label):
                self.assertEqual(response.status_code, expected, response.data)
                self.assertIn("detail", response.data)
        self.assertEqual(Event.objects.count(), 0)

    def test_missing_file_field(self):
        self.assertEqual(self.client.post(URL, {}, format="multipart").status_code, 400)

    @override_settings(MAX_UPLOAD_BYTES=50)
    def test_too_large(self):
        self.assertEqual(self.post(make_tgz({"a.log": line(1) * 5})).status_code, 413)

    def test_failed_import_leaves_no_rows_and_can_be_retried(self):
        data = make_tgz({"a.log": line(1), "b.log": line(2)})
        # First file's batch is flushed, the second one fails: everything must roll back.
        real_flush = __import__("events.services.ingestion_service", fromlist=["_flush"])._flush
        calls = {"n": 0}

        def flaky(batch, stats):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom")
            real_flush(batch, stats)

        self.client.raise_request_exception = False
        with mock.patch("events.services.ingestion_service._flush", side_effect=flaky):
            response = self.post(data)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(Event.objects.count(), 0)
        self.assertEqual(Ingestion.objects.get().status, "failed")
        self.assertEqual(self.post(data).status_code, 201)  # retry of the same bytes works
        self.assertEqual(Event.objects.count(), 2)

    def test_status_endpoints(self):
        self.post(make_tgz({"a.log": line(1)}))
        listing = self.client.get("/api/v1/ingestions/").data
        self.assertEqual(len(listing), 1)
        self.assertEqual(self.client.get(f"/api/v1/ingestions/{listing[0]['id']}/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/ingestions/999/").status_code, 404)
        summary = self.client.get("/api/v1/summary/").data
        self.assertEqual((summary["total_events"], summary["source_files"]), (1, 1))

    def test_health(self):
        self.assertEqual(self.client.get("/api/v1/health/").data, {"status": "ok"})
