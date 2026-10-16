from rest_framework.test import APITestCase

from ..fields import EVENT_FIELDS, FIELD_NAMES
from ..models import Event
from ..services.parser_service import parse_line
from .helpers import line

URL = "/api/v1/events/"


def make_event(serial, source="a.log", **over):
    return Event(source_file=source, **parse_line(line(serial, **over)))


class SearchApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Event.objects.bulk_create(
            [
                make_event(1, "a.log"),
                make_event(2, "a.log", srcaddr="10.0.0.2", dstport=80, action="ACCEPT", account_id="111"),
                make_event(3, "b.log", srcaddr="10.0.0.2", dstport=443, protocol=6, log_status="FAIL", version="5"),
                make_event(4, "b.log", instance_id="eni-999", packets=77, bytes=5, starttime=1, endtime=2, srcport=9),
                make_event(5, "b.log", dstaddr="8.8.8.8"),
            ]
        )

    def serials(self, response):
        return [r["serialno"] for r in response.data["results"]]

    def test_each_of_the_15_fields_searchable_individually(self):
        expected = {  # api field -> (query value, serials expected)
            "serialno": ("3", ["3"]),
            "version": ("5", ["3"]),
            "account-id": ("111", ["2"]),
            "instance-id": ("eni-999", ["4"]),
            "srcaddr": ("10.0.0.2", ["2", "3"]),
            "dstaddr": ("8.8.8.8", ["5"]),
            "srcport": ("9", ["4"]),
            "dstport": ("443", ["3"]),
            "protocol": ("6", ["3"]),
            "packets": ("77", ["4"]),
            "bytes": ("5", ["4"]),
            "starttime": ("1", ["4"]),
            "endtime": ("2", ["4"]),
            "action": ("ACCEPT", ["2"]),
            "log-status": ("FAIL", ["3"]),
        }
        self.assertEqual(set(expected), set(FIELD_NAMES))
        for name, (value, serials) in expected.items():
            with self.subTest(name):
                response = self.client.get(URL, {name: value})
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(self.serials(response), serials)
                self.assertEqual(response.data["count"], len(serials))

    def test_response_shape_and_all_fields_with_file(self):
        data = self.client.get(URL, {"serialno": "1"}).data
        self.assertEqual(
            set(data), {"count", "page", "page_size", "total_pages", "search_time_ms", "search_time_seconds", "results"}
        )
        self.assertEqual(
            data["results"][0],
            {
                "serialno": "1", "version": "2", "account-id": "348935949", "instance-id": "eni-293216456",
                "srcaddr": "159.62.125.136", "dstaddr": "30.55.177.194", "srcport": 152, "dstport": 23475,
                "protocol": 8, "packets": 10, "bytes": 3929334, "starttime": 1725850449, "endtime": 1725855086,
                "action": "REJECT", "log-status": "OK", "file": "a.log",
            },
        )
        self.assertEqual(len(data["results"][0]), len(EVENT_FIELDS) + 1)

    def test_search_time_fields(self):
        data = self.client.get(URL, {"action": "reject"}).data
        self.assertIsInstance(data["search_time_ms"], float)
        self.assertGreaterEqual(data["search_time_ms"], 0)
        self.assertAlmostEqual(data["search_time_ms"] / 1000, data["search_time_seconds"], places=4)

    def test_multiple_filters_use_and(self):
        self.assertEqual(self.serials(self.client.get(URL, {"srcaddr": "10.0.0.2", "dstport": "443"})), ["3"])
        self.assertEqual(self.serials(self.client.get(URL, {"srcaddr": "10.0.0.2", "dstport": "9999"})), [])
        response = self.client.get(
            URL, {"account-id": "348935949", "protocol": "8", "action": "REJECT", "log-status": "OK"}
        )
        self.assertEqual(self.serials(response), ["1", "4", "5"])

    def test_blank_filters_ignored(self):
        response = self.client.get(URL, {"srcaddr": "10.0.0.2", "dstport": "   ", "action": ""})
        self.assertEqual(self.serials(response), ["2", "3"])

    def test_empty_search_rejected(self):
        for params in ({}, {"srcaddr": "  ", "action": ""}, {"page": "2"}):
            with self.subTest(params=params):
                response = self.client.get(URL, params)
                self.assertEqual(response.status_code, 400)
                self.assertIn("non_field_errors", response.data["errors"])

    def test_case_insensitive_enums_and_exact_matching(self):
        self.assertEqual(self.serials(self.client.get(URL, {"action": "accept"})), ["2"])
        self.assertEqual(self.serials(self.client.get(URL, {"log-status": "fail"})), ["3"])
        self.assertEqual(self.client.get(URL, {"srcaddr": "10.0.0"}).status_code, 400)  # no partial match
        self.assertEqual(self.client.get(URL, {"instance-id": "eni-99"}).data["count"], 0)

    def test_validation_errors(self):
        bad = [
            {"srcport": "abc"}, {"dstport": "-1"}, {"bytes": "1.5"}, {"srcaddr": "300.1.1.1"},
            {"serialno": "12x"}, {"protocol": "99999999999"}, {"action": "RE JECT"},
        ]
        for params in bad:
            with self.subTest(params=params):
                response = self.client.get(URL, params)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(set(response.data["errors"]), set(params))

    def test_unsupported_and_repeated_params(self):
        response = self.client.get(URL, {"srcaddr": "10.0.0.2", "colour": "red"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("colour", response.data["errors"])
        self.assertEqual(self.client.get(URL + "?srcport=1&srcport=2").status_code, 400)
        self.assertEqual(self.client.get(URL, {"action": "ACCEPT", "page_size": "0"}).status_code, 400)
        self.assertEqual(self.client.get(URL, {"action": "ACCEPT", "page_size": "9999"}).status_code, 400)
        self.assertEqual(self.client.get(URL, {"action": "ACCEPT", "page": "x"}).status_code, 400)

    def test_sql_injection_attempt_is_just_an_invalid_value(self):
        response = self.client.get(URL, {"instance-id": "x' OR '1'='1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(Event.objects.count(), 5)

    def test_no_matches_and_empty_dataset(self):
        data = self.client.get(URL, {"srcport": "55555"}).data
        self.assertEqual((data["count"], data["results"], data["total_pages"]), (0, [], 0))
        Event.objects.all().delete()
        self.assertEqual(self.client.get(URL, {"action": "ACCEPT"}).data["count"], 0)

    def test_pagination_counts_and_stable_order(self):
        Event.objects.bulk_create([make_event(100 + i, "c.log", srcport=7777) for i in range(25)])
        seen = []
        for page in (1, 2, 3):
            data = self.client.get(URL, {"srcport": "7777", "page": page, "page_size": 10}).data
            self.assertEqual((data["count"], data["total_pages"], data["page"], data["page_size"]), (25, 3, page, 10))
            seen += [r["serialno"] for r in data["results"]]
        self.assertEqual(seen, [str(100 + i) for i in range(25)])  # complete, ordered, no overlap
        self.assertEqual(len(self.client.get(URL, {"srcport": "7777", "page": 3, "page_size": 10}).data["results"]), 5)
        beyond = self.client.get(URL, {"srcport": "7777", "page": 4, "page_size": 10}).data
        self.assertEqual((beyond["results"], beyond["count"]), ([], 25))

    def test_default_page_size(self):
        self.assertEqual(self.client.get(URL, {"action": "REJECT"}).data["page_size"], 50)

    def test_unknown_route_and_method_errors_are_json(self):
        self.assertEqual(self.client.post(URL, {}).status_code, 405)
        self.assertIn("detail", self.client.post(URL, {}).data)
        self.assertEqual(self.client.get("/api/v1/nope/").status_code, 404)

    def test_query_count_is_constant(self):
        with self.assertNumQueries(2):  # COUNT + page
            self.client.get(URL, {"srcaddr": "10.0.0.2"})
