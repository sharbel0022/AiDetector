"""Atomic quotas for workers on one host. Never stores text or bearer credentials."""
from contextlib import contextmanager
import hashlib
import secrets
import sqlite3
import threading
import time

from fastapi import HTTPException


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

    def reserve(self, principal: str, tokens: int, settings, timeout: float) -> str:
        """Reserve a worst-case token allowance, including failed/cancelled calls.

        UTF-8 byte counts bound input tokens conservatively, rather than estimating
        cost using an arbitrary model's tokenizer. Provider billing is separate.
        """
        now = time.time()
        day = int(now // 86400)
        key = hashlib.sha256(principal.encode()).hexdigest()
        lease = secrets.token_hex(16)
        with self.transaction() as db:
            db.execute('DELETE FROM leases WHERE expires <= ?', (now,))
            db.execute('DELETE FROM budgets WHERE day < ?', (day,))
            if db.execute('SELECT count(*) FROM leases').fetchone()[0] >= settings.max_concurrent:
                raise HTTPException(429, 'Serverns AI-anrop är upptagna. Försök senare.', headers={'Retry-After': '5'})
            for owner, limit in [(key, settings.daily_token_budget), ('global', settings.global_daily_token_budget)]:
                row = db.execute('SELECT used FROM budgets WHERE principal = ? AND day = ?', (owner, day)).fetchone()
                if (row[0] if row else 0) + tokens > limit:
                    raise HTTPException(429, 'Dagens AI-budget är förbrukad. Försök nästa UTC-dygn.', headers={'Retry-After': str(max(1, int((day + 1) * 86400 - now)))})
            for owner in (key, 'global'):
                db.execute('INSERT INTO budgets VALUES (?, ?, ?) ON CONFLICT(principal, day) DO UPDATE SET used = used + excluded.used', (owner, day, tokens))
            db.execute('INSERT INTO leases VALUES (?, ?)', (lease, now + timeout + 5))
        return lease

    def release(self, lease: str):
        with self.transaction() as db:
            db.execute('DELETE FROM leases WHERE id = ?', (lease,))
