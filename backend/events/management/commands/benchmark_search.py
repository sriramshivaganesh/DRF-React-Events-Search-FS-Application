"""Benchmark representative searches against the data already imported.

Query values are taken from a real stored row so every query has matches.
Timing uses the same function (and thus the same timed block) as the API.
"""
import statistics

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from events.fields import EVENT_FIELDS
from events.models import Event
from events.services.search_service import SearchRequest, search_events


class Command(BaseCommand):
    help = "Time single-field and multi-field searches and print SQLite query plans."

    def add_arguments(self, parser):
        parser.add_argument("--runs", type=int, default=30)
        parser.add_argument("--plans", action="store_true", help="also print EXPLAIN QUERY PLAN")

    def handle(self, *args, runs: int, plans: bool, **options):
        total = Event.objects.count()
        if not total:
            raise CommandError("No events imported.")
        sample = Event.objects.order_by("id")[total // 2]
        value = {spec.api_name: getattr(sample, spec.attr) for spec in EVENT_FIELDS}
        attr = {spec.api_name: spec.attr for spec in EVENT_FIELDS}

        def q(*names):
            return {attr[n]: value[n] for n in names}

        cases = [(f"{spec.api_name}", q(spec.api_name)) for spec in EVENT_FIELDS]
        cases += [
            ("srcaddr+dstport", q("srcaddr", "dstport")),
            ("account-id+protocol+action+log-status", q("account-id", "protocol", "action", "log-status")),
            ("action+log-status+protocol+version", q("action", "log-status", "protocol", "version")),
            ("all 15 fields", q(*[s.api_name for s in EVENT_FIELDS])),
            ("action+bytes", q("action", "bytes")),
        ]
        self.stdout.write(f"events in database: {total}; runs per query: {runs}\n")
        self.stdout.write(f"{'query':45} {'matches':>8} {'median ms':>10} {'min ms':>8} {'max ms':>8}")
        for label, filters in cases:
            request = SearchRequest(filters, 1, 50)
            search_events(request)  # warm-up
            times = []
            for _ in range(runs):
                outcome = search_events(request)
                times.append(outcome.elapsed_seconds * 1000)
            self.stdout.write(
                f"{label:45} {outcome.count:>8} {statistics.median(times):>10.3f} {min(times):>8.3f} {max(times):>8.3f}"
            )
            if plans:
                sql, params = Event.objects.filter(**filters).order_by("id").values("id")[:50].query.sql_with_params()
                with connection.cursor() as cursor:
                    cursor.execute("EXPLAIN QUERY PLAN " + sql, params)
                    for row in cursor.fetchall():
                        self.stdout.write(f"    plan: {row[3]}")
