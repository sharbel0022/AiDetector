"""Atomic quotas for workers on one host. Never stores text or bearer credentials."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import secrets
import sqlite3
import threading
import time

from fastapi import HTTPException

from ai.usage import amount_to_nanos, counter, MODEL_ID, safe_latency


class SharedLimits:
    def __init__(self, path: str):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path or ':memory:', timeout=.2, check_same_thread=False, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS requests (principal TEXT, at REAL);
            CREATE INDEX IF NOT EXISTS requests_lookup ON requests(principal, at);
            CREATE TABLE IF NOT EXISTS budgets (principal TEXT, day INTEGER, used INTEGER, PRIMARY KEY(principal, day));
            CREATE TABLE IF NOT EXISTS leases (id TEXT PRIMARY KEY, expires REAL);
            CREATE TABLE IF NOT EXISTS cost_budgets (principal TEXT, day INTEGER, used INTEGER, PRIMARY KEY(principal, day));
            CREATE TABLE IF NOT EXISTS usage_events (
                id TEXT PRIMARY KEY, principal TEXT NOT NULL, day INTEGER NOT NULL,
                created_at REAL NOT NULL, completed_at REAL, status TEXT NOT NULL,
                application_status TEXT NOT NULL DEFAULT 'not_evaluated',
                provider TEXT, requested_model TEXT, model TEXT, latency_ms REAL,
                input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER,
                cached_input_tokens INTEGER, total_tokens_source TEXT,
                estimated_cost_nanos INTEGER, pricing_version TEXT, cost_status TEXT NOT NULL DEFAULT 'unknown',
                reserved_tokens INTEGER NOT NULL, reserved_cost_nanos INTEGER,
                charged_tokens INTEGER NOT NULL, charged_cost_nanos INTEGER
            );
            CREATE INDEX IF NOT EXISTS usage_principal_day ON usage_events(principal, day);
        ''')

    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                self.db.execute('BEGIN IMMEDIATE')
                yield self.db
                self.db.execute('COMMIT')
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute('ROLLBACK')
                raise

    def rate(self, principal: str, per_minute: int):
        now = time.time()
        key = hashlib.sha256(principal.encode()).hexdigest()
        with self.transaction() as db:
            db.execute('DELETE FROM requests WHERE at <= ?', (now - 60,))
            count = db.execute('SELECT count(*) FROM requests WHERE principal = ?', (key,)).fetchone()[0]
            if count >= per_minute:
                raise HTTPException(429, 'För många anrop. Försök om en minut.', headers={'Retry-After': '60'})
            db.execute('INSERT INTO requests VALUES (?, ?)', (key, now))

    @staticmethod
    def _purge(db, day, now):
        # Retain the current UTC day plus the preceding 30 days. Both generation
        # and authenticated reads perform cleanup; an idle service has no timer.
        db.execute('DELETE FROM leases WHERE expires <= ?', (now,))
        db.execute('DELETE FROM budgets WHERE day < ?', (day - 30,))
        db.execute('DELETE FROM cost_budgets WHERE day < ?', (day - 30,))
        db.execute('DELETE FROM usage_events WHERE day < ?', (day - 30,))

    def reserve(self, principal: str, tokens: int, settings, timeout: float, *, cost_nanos: int | None = None) -> str:
        """Reserve a worst-case token allowance, including failed/cancelled calls.

        A row and both quota charges commit before sending the provider request.
        Unknown or interrupted usage keeps this allowance; known usage can later
        reconcile it atomically. A dead worker's expiring concurrency lease never
        removes its token/currency allowance.
        """
        now = time.time()
        day = int(now // 86400)
        key = hashlib.sha256(principal.encode()).hexdigest()
        lease = secrets.token_hex(16)
        with self.transaction() as db:
            self._purge(db, day, now)
            if db.execute('SELECT count(*) FROM leases').fetchone()[0] >= settings.max_concurrent:
                raise HTTPException(429, 'Serverns AI-anrop är upptagna. Försök senare.', headers={'Retry-After': '5'})
            for owner, limit in [(key, settings.daily_token_budget), ('global', settings.global_daily_token_budget)]:
                row = db.execute('SELECT used FROM budgets WHERE principal = ? AND day = ?', (owner, day)).fetchone()
                if (row[0] if row else 0) + tokens > limit:
                    raise HTTPException(429, 'Dagens AI-budget är förbrukad. Försök nästa UTC-dygn.', headers={'Retry-After': str(max(1, int((day + 1) * 86400 - now)))})
            for owner, limit in [(key, settings.daily_cost_budget_usd), ('global', settings.global_daily_cost_budget_usd)]:
                if limit is None:
                    continue
                if cost_nanos is None:
                    raise HTTPException(503, 'Kostnadsgränsen kräver ett verifierat pris för serverns modell. Ingen AI-begäran skickades.')
                recorded_tokens, unpriced = db.execute('''SELECT COALESCE(SUM(charged_tokens), 0),
                    COUNT(CASE WHEN charged_cost_nanos IS NULL AND cost_status != 'not_applicable' THEN 1 END)
                    FROM usage_events WHERE day = ? AND (? = 'global' OR principal = ?)''', (day, owner, owner)).fetchone()
                token_row = db.execute('SELECT used FROM budgets WHERE principal = ? AND day = ?', (owner, day)).fetchone()
                # A V4 database or earlier unpriced model has no currency ceiling
                # to reconcile. Enabling a cap must not pretend that spend was 0.
                if unpriced or (token_row[0] if token_row else 0) > recorded_tokens:
                    raise HTTPException(503, 'Kostnadsbudgeten kan inte verifieras efter tidigare anrop utan prisdata. Försök nästa UTC-dygn.')
                row = db.execute('SELECT used FROM cost_budgets WHERE principal = ? AND day = ?', (owner, day)).fetchone()
                if (row[0] if row else 0) + cost_nanos > amount_to_nanos(limit, ceiling=False):
                    raise HTTPException(429, 'Dagens kostnadsbudget är förbrukad. Försök nästa UTC-dygn.', headers={'Retry-After': str(max(1, int((day + 1) * 86400 - now)))})
            for owner in (key, 'global'):
                db.execute('INSERT INTO budgets VALUES (?, ?, ?) ON CONFLICT(principal, day) DO UPDATE SET used = used + excluded.used', (owner, day, tokens))
                if cost_nanos is not None:
                    db.execute('INSERT INTO cost_budgets VALUES (?, ?, ?) ON CONFLICT(principal, day) DO UPDATE SET used = used + excluded.used', (owner, day, cost_nanos))
            db.execute('INSERT INTO leases VALUES (?, ?)', (lease, now + timeout + 5))
            model = settings.model if isinstance(settings.model, str) and MODEL_ID.fullmatch(settings.model) else None
            db.execute('''INSERT INTO usage_events
                (id, principal, day, created_at, status, provider, requested_model,
                 reserved_tokens, reserved_cost_nanos, charged_tokens, charged_cost_nanos)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)''',
                (lease, key, day, now, settings.provider, model, tokens, cost_nanos, tokens, cost_nanos))
        return lease

    def release(self, lease: str):
        self.complete(lease, None, 'unreported')

    def complete(self, lease: str, usage: dict | None, status: str):
        """Idempotent settlement; no counters means no refund, including failures."""
        if status not in ('provider_success', 'failed', 'cancelled', 'timeout', 'unreported'):
            raise ValueError('Invalid usage status')
        usage = usage if isinstance(usage, dict) else {}
        counts = {name: counter(usage.get(name)) for name in ('input_tokens', 'output_tokens', 'total_tokens', 'cached_input_tokens')}
        actual = counts['total_tokens']
        if counts['input_tokens'] is not None and counts['output_tokens'] is not None and actual != counts['input_tokens'] + counts['output_tokens']:
            actual = None
            counts['total_tokens'] = None
        cost = usage.get('cost') if isinstance(usage.get('cost'), dict) else {}
        amount = cost.get('estimated_amount')
        cost_known = cost.get('status') == 'estimated' and cost.get('currency') == 'USD' and type(amount) in (int, float) and isinstance(cost.get('pricing_version'), str)
        try:
            cost_nanos = amount_to_nanos(amount) if cost_known else None
        except ValueError:
            cost_nanos, cost_known = None, False
        with self.transaction() as db:
            row = db.execute('SELECT principal, day, reserved_tokens, reserved_cost_nanos, completed_at FROM usage_events WHERE id = ?', (lease,)).fetchone()
            if row is None or row[4] is not None:
                return
            principal, day, reserved_tokens, reserved_cost, _ = row
            charge_tokens = actual if actual is not None else reserved_tokens
            charge_cost = cost_nanos if cost_nanos is not None else reserved_cost
            for owner in (principal, 'global'):
                db.execute('UPDATE budgets SET used = used + ? WHERE principal = ? AND day = ?', (charge_tokens - reserved_tokens, owner, day))
                # Upsert preserves an actual priced result even if no price was
                # known at reservation time. A day boundary never charges a new day.
                delta = (charge_cost or 0) - (reserved_cost or 0)
                db.execute('INSERT INTO cost_budgets VALUES (?, ?, ?) ON CONFLICT(principal, day) DO UPDATE SET used = used + excluded.used', (owner, day, delta))
            model = usage.get('model')
            model = model if isinstance(model, str) and MODEL_ID.fullmatch(model) else None
            db.execute('''UPDATE usage_events SET completed_at = ?, status = ?, model = ?, latency_ms = ?,
                input_tokens = ?, output_tokens = ?, total_tokens = ?, cached_input_tokens = ?, total_tokens_source = ?,
                estimated_cost_nanos = ?, pricing_version = ?, cost_status = ?, charged_tokens = ?, charged_cost_nanos = ?
                WHERE id = ?''', (time.time(), status, model, safe_latency(usage.get('latency_ms')),
                counts['input_tokens'], counts['output_tokens'], counts['total_tokens'], counts['cached_input_tokens'], usage.get('total_tokens_source', 'unknown'),
                cost_nanos, cost.get('pricing_version') if cost_known else None,
                'estimated' if cost_known else ('not_applicable' if cost.get('status') == 'not_applicable' else 'unknown'), charge_tokens, charge_cost, lease))
            db.execute('DELETE FROM leases WHERE id = ?', (lease,))

    def application_result(self, lease: str, status: str):
        if status not in ('accepted', 'rejected', 'probe'):
            raise ValueError('Invalid application status')
        with self.transaction() as db:
            db.execute('UPDATE usage_events SET application_status = ? WHERE id = ?', (status, lease))

    def summary(self, principal: str, settings) -> dict:
        """Today's own counters; partial totals explicitly report missing records."""
        now = time.time()
        day = int(now // 86400)
        key = hashlib.sha256(principal.encode()).hexdigest()
        with self.transaction() as db:
            self._purge(db, day, now)
            db.execute("UPDATE usage_events SET status = 'unreported' WHERE status = 'pending' AND id NOT IN (SELECT id FROM leases WHERE expires > ?)", (now,))
            rows = db.execute('''SELECT input_tokens, output_tokens, total_tokens, cached_input_tokens,
                estimated_cost_nanos, cost_status, status, charged_tokens, charged_cost_nanos,
                application_status FROM usage_events WHERE principal = ? AND day = ?''', (key, day)).fetchall()
            token_row = db.execute('SELECT used FROM budgets WHERE principal = ? AND day = ?', (key, day)).fetchone()
            cost_row = db.execute('SELECT used FROM cost_budgets WHERE principal = ? AND day = ?', (key, day)).fetchone()
            models = db.execute('''SELECT provider, model, requested_model, COUNT(*) FROM usage_events
                WHERE principal = ? AND day = ? GROUP BY provider, model, requested_model''', (key, day)).fetchall()
        charged_tokens = token_row[0] if token_row else 0
        charged_cost = cost_row[0] if cost_row else 0
        legacy_reserved = max(0, charged_tokens - sum(row[7] for row in rows))
        names = ('input_tokens', 'output_tokens', 'total_tokens', 'cached_input_tokens')
        counters, missing = {}, {}
        for index, name in enumerate(names):
            reported = [row[index] for row in rows if row[index] is not None]
            counters[name] = sum(reported) if reported or (not rows and not legacy_reserved) else None
            missing[name] = len(rows) - len(reported)
        known_costs = [row[4] for row in rows if row[4] is not None]
        iso = lambda timestamp: datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace('+00:00', 'Z')
        return {
            'period': {'start': iso(day * 86400), 'end': iso((day + 1) * 86400), 'timezone': 'UTC'},
            'requests': len(rows), **counters, 'unreported_counters': missing,
            'estimated_cost': {'currency': 'USD', 'amount': sum(known_costs) / 1_000_000_000 if known_costs or (not rows and not legacy_reserved) else None,
                               'unknown_requests': sum(row[5] == 'unknown' for row in rows),
                               'not_applicable_requests': sum(row[5] == 'not_applicable' for row in rows)},
            'reservations': {'tokens': legacy_reserved + sum(row[7] for row in rows if row[2] is None),
                             'legacy_reserved_tokens': legacy_reserved,
                             'cost_usd': sum(row[8] or 0 for row in rows if row[4] is None) / 1_000_000_000,
                             'pending_requests': sum(row[6] == 'pending' for row in rows),
                             'unreported_requests': sum(row[2] is None and row[6] != 'pending' for row in rows)},
            'budget': {'daily_token_limit': settings.daily_token_budget, 'charged_tokens': charged_tokens,
                       'remaining_tokens': max(0, settings.daily_token_budget - charged_tokens),
                       'daily_cost_limit_usd': settings.daily_cost_budget_usd,
                       'charged_cost_usd': charged_cost / 1_000_000_000,
                       'remaining_cost_usd': max(0, settings.daily_cost_budget_usd - charged_cost / 1_000_000_000) if settings.daily_cost_budget_usd is not None else None,
                       'accounting': 'provider_usage_when_reported_otherwise_reserved'},
            'outcomes': {status: sum(row[9] == status for row in rows) for status in ('accepted', 'rejected', 'probe', 'not_evaluated')},
            'models': [{'provider': row[0], 'model': row[1], 'requested_model': row[2], 'requests': row[3]} for row in models],
            'retention_days': 31, 'text_storage': False, 'legacy_usage_unavailable': bool(legacy_reserved),
        }
