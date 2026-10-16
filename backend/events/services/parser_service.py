"""Parsing of event log lines.

Observed format (supplied archive): plain text, no header, one event per line,
15 whitespace-separated values in the order of EVENT_FIELDS. The parser also
tolerates an optional header line and "-" for missing values (AWS flow-log
style NODATA/SKIPDATA records), which are stored as NULL.
"""
import ipaddress
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from ..fields import EVENT_FIELDS, FIELD_NAMES, FieldSpec


class ParseError(ValueError):
    pass


@dataclass
class ParsedLine:
    line_no: int
    values: dict | None = None  # model attr -> python value
    error: str | None = None


def validate_value(spec: FieldSpec, raw: str):
    """Validate/normalise one value for `spec`. Shared by ingestion and search."""
    kind = spec.kind
    if kind == "digits":
        if not (raw.isascii() and raw.isdigit()):
            raise ParseError(f"{spec.api_name} must contain digits only")
        if len(raw) > 32:
            raise ParseError(f"{spec.api_name} is too long")
        return raw
    if kind == "token":
        if len(raw) > 64:
            raise ParseError(f"{spec.api_name} is too long")
        return raw
    if kind == "ip":
        try:
            return str(ipaddress.ip_address(raw))  # canonical form (e.g. compressed IPv6)
        except ValueError:
            raise ParseError(f"{spec.api_name} must be a valid IPv4/IPv6 address") from None
    if kind == "int":
        if not (raw.isascii() and raw.isdigit()):
            raise ParseError(f"{spec.api_name} must be a non-negative integer")
        value = int(raw)
        if value > spec.max_value:
            raise ParseError(f"{spec.api_name} must be <= {spec.max_value}")
        return value
    if kind == "enum":
        if len(raw) > 16 or not raw.replace("_", "").isalnum():
            raise ParseError(f"{spec.api_name} must be a short alphanumeric word")
        return raw.upper()  # case-insensitive policy: canonical upper-case
    raise AssertionError(kind)


def parse_line(line: str) -> dict:
    parts = line.split()  # any run of spaces/tabs is a delimiter
    if len(parts) != len(EVENT_FIELDS):
        raise ParseError(f"expected {len(EVENT_FIELDS)} fields, found {len(parts)}")
    values = {}
    for spec, raw in zip(EVENT_FIELDS, parts):
        if raw == "-" and spec.api_name != "serialno":
            values[spec.attr] = None
            continue
        values[spec.attr] = validate_value(spec, raw)
    return values


def _is_header(line: str) -> bool:
    return [p.lower().replace("_", "-") for p in line.split()] == list(FIELD_NAMES)


def iter_parsed_lines(lines: Iterable[str]) -> Iterator[ParsedLine]:
    """Yield a ParsedLine per non-blank line; skips a header line if present."""
    first = True
    for line_no, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        if first:
            first = False
            if _is_header(line):
                continue
        try:
            yield ParsedLine(line_no, values=parse_line(line))
        except ParseError as exc:
            yield ParsedLine(line_no, error=str(exc))
