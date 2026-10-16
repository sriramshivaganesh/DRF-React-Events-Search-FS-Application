"""Single source of truth for the 15 event fields and their external (API) names.

The external names come from the assignment (`account-id`, `log-status` contain
hyphens, so they cannot be Python identifiers). Each spec maps the external name
to the Django model attribute and describes how values are validated.
"""
from dataclasses import dataclass

INT64_MAX = 2**63 - 1
# The supplied data contains ports above 65535 (up to 102400), so ports/protocol are
# only bounded by what a signed 32-bit column can hold, not by the TCP/IP ranges.
INT32_MAX = 2**31 - 1


@dataclass(frozen=True)
class FieldSpec:
    api_name: str  # name used in log files, query strings and JSON
    attr: str  # Django model attribute
    kind: str  # "digits" | "token" | "ip" | "int" | "enum"
    label: str  # human-readable label (mirrored by the frontend)
    max_value: int = INT64_MAX  # upper bound for "int" kinds


EVENT_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("serialno", "serialno", "digits", "Serial Number"),
    FieldSpec("version", "version", "digits", "Version"),
    FieldSpec("account-id", "account_id", "digits", "Account ID"),
    FieldSpec("instance-id", "instance_id", "token", "Instance ID"),
    FieldSpec("srcaddr", "srcaddr", "ip", "Source IP Address"),
    FieldSpec("dstaddr", "dstaddr", "ip", "Destination IP Address"),
    FieldSpec("srcport", "srcport", "int", "Source Port", INT32_MAX),
    FieldSpec("dstport", "dstport", "int", "Destination Port", INT32_MAX),
    FieldSpec("protocol", "protocol", "int", "Protocol", INT32_MAX),
    FieldSpec("packets", "packets", "int", "Packets"),
    FieldSpec("bytes", "bytes", "int", "Bytes"),
    FieldSpec("starttime", "starttime", "int", "Start Time (epoch)"),
    FieldSpec("endtime", "endtime", "int", "End Time (epoch)"),
    FieldSpec("action", "action", "enum", "Action"),
    FieldSpec("log-status", "log_status", "enum", "Log Status"),
)

FIELD_BY_API_NAME = {f.api_name: f for f in EVENT_FIELDS}
FIELD_NAMES = tuple(f.api_name for f in EVENT_FIELDS)
# Name of the extra response key carrying the source filename.
FILE_KEY = "file"
