from django.test import SimpleTestCase

from ..services.parser_service import ParseError, iter_parsed_lines, parse_line
from .helpers import SAMPLE, line


class ParserTests(SimpleTestCase):
    def test_parses_valid_record_with_all_15_fields(self):
        values = parse_line(SAMPLE)
        self.assertEqual(len(values), 15)
        self.assertEqual(values["serialno"], "1")
        self.assertEqual(values["account_id"], "348935949")
        self.assertEqual(values["srcport"], 152)
        self.assertEqual(values["bytes"], 3929334)
        self.assertEqual(values["action"], "REJECT")
        self.assertEqual(values["log_status"], "OK")

    def test_preserves_leading_zeros_in_identifiers(self):
        values = parse_line(line("007", account_id="000123"))
        self.assertEqual((values["serialno"], values["account_id"]), ("007", "000123"))

    def test_accepts_tabs_and_normalises_case(self):
        values = parse_line(SAMPLE.replace(" ", "\t").replace("REJECT", "reject"))
        self.assertEqual(values["action"], "REJECT")

    def test_ports_above_65535_are_accepted(self):
        # The supplied dataset contains such values (up to 102400).
        self.assertEqual(parse_line(line(1, dstport=102400))["dstport"], 102400)

    def test_dash_means_null(self):
        values = parse_line(line(5, srcaddr="-", srcport="-", log_status="NODATA"))
        self.assertIsNone(values["srcaddr"])
        self.assertIsNone(values["srcport"])

    def test_malformed_records_raise(self):
        bad_lines = ["", "1 2 3", SAMPLE + " extra", line(1, srcaddr="999.1.1.1"), line(1, srcport="abc"), line(1, bytes="-5")]
        for bad in bad_lines:
            with self.subTest(bad=bad), self.assertRaises(ParseError):
                parse_line(bad)

    def test_header_and_blank_lines_skipped_and_errors_reported(self):
        header = (
            "serialno version account-id instance-id srcaddr dstaddr srcport dstport "
            "protocol packets bytes starttime endtime action log-status"
        )
        parsed = list(iter_parsed_lines([header, "", line(1), "garbage"]))
        self.assertEqual(len(parsed), 2)
        self.assertIsNotNone(parsed[0].values)
        self.assertIsNotNone(parsed[1].error)
        self.assertEqual(parsed[1].line_no, 4)
