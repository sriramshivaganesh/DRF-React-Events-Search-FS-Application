"""Search over stored events.

Semantics (documented in the README):
* Every supplied, non-blank filter is combined with AND.
* Blank / whitespace-only filters are ignored.
* All matching is exact equality. `action` and `log-status` are compared
  case-insensitively because both the stored value and the query are
  canonicalised to upper case (keeps the comparison indexable).
* At least one non-blank filter is required; an empty search is rejected.
"""
import math
import time
from collections.abc import Mapping
from dataclasses import dataclass

from django.conf import settings
from rest_framework.exceptions import ValidationError

from ..fields import EVENT_FIELDS, FIELD_BY_API_NAME
from ..models import Event
from .parser_service import ParseError, validate_value

PAGING_PARAMS = ("page", "page_size")


@dataclass
class SearchRequest:
    filters: dict  # model attr -> validated value
    page: int
    page_size: int


@dataclass
class SearchOutcome:
    count: int
    rows: list[dict]
    elapsed_seconds: float
    total_pages: int


def _parse_positive_int(raw: str, name: str, maximum: int | None, errors: dict) -> int | None:
    raw = raw.strip()
    if not (raw.isascii() and raw.isdigit()) or int(raw) < 1:
        errors[name] = [f"{name} must be a positive integer."]
        return None
    value = int(raw)
    if maximum is not None and value > maximum:
        errors[name] = [f"{name} must be <= {maximum}."]
        return None
    return value


def parse_search_request(params: Mapping) -> SearchRequest:
    """Validate query-string parameters. `params` is a QueryDict (or any mapping with getlist)."""
    errors: dict[str, list[str]] = {}
    filters: dict = {}
    getlist = params.getlist if hasattr(params, "getlist") else lambda k: [params[k]]
    page, page_size = 1, settings.DEFAULT_PAGE_SIZE

    for name in params.keys():
        values = getlist(name)
        if name in PAGING_PARAMS:
            if len(values) > 1:
                errors[name] = [f"{name} may only be given once."]
            elif name == "page":
                page = _parse_positive_int(values[0], name, None, errors) or page
            else:
                page_size = _parse_positive_int(values[0], name, settings.MAX_PAGE_SIZE, errors) or page_size
            continue
        spec = FIELD_BY_API_NAME.get(name)
        if spec is None:
            errors[name] = ["Unsupported search field."]
            continue
        if len(values) > 1:
            errors[name] = [f"{name} may only be given once."]
            continue
        raw = values[0].strip()
        if not raw:
            continue  # blank filters are ignored
        try:
            filters[spec.attr] = validate_value(spec, raw)
        except ParseError as exc:
            errors[name] = [str(exc)]

    if not errors and not filters:
        errors["non_field_errors"] = [
            "At least one search field is required; empty searches are not allowed. "
            f"Supported fields: {', '.join(f.api_name for f in EVENT_FIELDS)}."
        ]
    if errors:
        raise ValidationError(errors)
    return SearchRequest(filters, page, page_size)


# Columns fetched from the DB; `.values()` avoids building model instances.
RESULT_COLUMNS = [f.attr for f in EVENT_FIELDS] + ["source_file"]


def search_events(request: SearchRequest) -> SearchOutcome:
    """Run COUNT + one page query. Only this block is timed (see README)."""
    queryset = Event.objects.filter(**request.filters)  # parameterised by the ORM
    offset = (request.page - 1) * request.page_size

    started = time.perf_counter()
    count = queryset.count()
    rows = []
    if count > offset:
        # Deterministic order: primary key (insertion order).
        rows = list(queryset.order_by("id").values(*RESULT_COLUMNS)[offset : offset + request.page_size])
    elapsed = time.perf_counter() - started

    return SearchOutcome(count, rows, elapsed, math.ceil(count / request.page_size))
