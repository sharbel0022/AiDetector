"""Text-free provider counters and explicitly versioned price estimates.

Provider counters are never inferred from source/output length. A derived total
is labelled when the provider reports only its input and output counts. Unknown
prices, cache counts or model IDs remain unknown, including compatible endpoints
that happen to use an OpenAI model name. Prices are an estimate, not an invoice.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from urllib.parse import urlparse

PRICE_FILE = Path(__file__).resolve().parent.parent / 'config' / 'model-prices.json'
MODEL_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,159}\Z')
COUNTERS = ('input_tokens', 'output_tokens', 'total_tokens', 'cached_input_tokens')
MAX_SQL_INTEGER = 2**63 - 1


class GenerationResult(str):
    """Existing string callers keep working; metadata survives until restoration."""
    def __new__(cls, text: str, usage: dict):
        result = super().__new__(cls, text)
        result.usage = usage
        return result


def counter(value) -> int | None:
    # SQLite and JavaScript can represent these counts exactly. Booleans, floats,
    # strings, negative and excessive values are not provider token counters.
    return value if type(value) is int and 0 <= value <= 2**53 - 1 else None


def safe_latency(value) -> float | None:
    return round(value, 3) if type(value) in (int, float) and 0 <= value <= 86_400_000 and math.isfinite(value) else None


def load_price_table(path: Path = PRICE_FILE) -> dict:
    """Validate the entire checked-in table before using any of its prices."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema_version') != 1 or data.get('currency') != 'USD' or data.get('unit') != 'per_1000000_tokens':
        raise ValueError('Unsupported price table')
    if not isinstance(data.get('version'), str) or not re.fullmatch(r'[0-9.\-]{1,40}', data['version']) or not isinstance(data.get('models'), list):
        raise ValueError('Invalid price version or model table')
    entries = {}
    for row in data['models']:
        if not isinstance(row, dict) or row.get('provider') != 'openai' or not isinstance(row.get('ids'), list) or not row['ids']:
            raise ValueError('Invalid priced provider or model IDs')
        source = urlparse(row.get('source', ''))
        if source.scheme != 'https' or source.hostname not in ('developers.openai.com', 'platform.openai.com') or source.username or source.password:
            raise ValueError('Prices require an official source')
        date.fromisoformat(row['verified_at'])
        prices = {}
        for name in ('input', 'cached_input', 'output'):
            value = row.get(name)
            if not isinstance(value, str):
                raise ValueError('Prices must be decimal strings')
            amount = Decimal(value)
            if not amount.is_finite() or amount < 0 or amount > 1000000:
                raise ValueError('Invalid model price')
            prices[name] = amount
        if prices['cached_input'] > prices['input']:
            raise ValueError('Invalid cached input price')
        for model in row['ids']:
            if not isinstance(model, str) or not MODEL_ID.fullmatch(model) or ('openai', model) in entries:
                raise ValueError('Invalid or duplicate priced model ID')
            entries['openai', model] = {**prices, 'version': data['version'], 'source': row['source'], 'verified_at': row['verified_at']}
    return entries


@lru_cache(maxsize=1)
def _prices() -> dict:
    try:
        return load_price_table()
    except (OSError, ValueError, TypeError, KeyError, InvalidOperation):
        # A corrupt or absent table cannot silently imply free usage.
        return {}


def amount_to_nanos(amount, *, ceiling=True) -> int:
    try:
        value = Decimal(str(amount)) * 1_000_000_000
    except InvalidOperation:
        raise ValueError('Invalid currency amount') from None
    if not value.is_finite() or not 0 <= value <= MAX_SQL_INTEGER:
        raise ValueError('Invalid currency amount')
    return int(value.to_integral_value(rounding=ROUND_CEILING if ceiling else ROUND_FLOOR))


def reservation_cost_nanos(provider: str, model: str, input_bound: int, output_cap: int) -> int | None:
    """Conservative standard-tier ceiling, assuming no cache discount."""
    row = _prices().get((provider, model))
    if row is None:
        return None
    return amount_to_nanos((input_bound * row['input'] + output_cap * row['output']) / 1_000_000)


def provider_usage(provider: str, data: dict | None, latency_ms: float) -> dict:
    data = data if isinstance(data, dict) else {}
    model = data.get('model')
    model = model if isinstance(model, str) and MODEL_ID.fullmatch(model) else None
    raw = data.get('usage') if isinstance(data.get('usage'), dict) else {}
    if provider == 'ollama':
        input_tokens, output_tokens = counter(data.get('prompt_eval_count')), counter(data.get('eval_count'))
        total_tokens, cached = None, None
    else:
        input_key, output_key, detail_key = ('input_tokens', 'output_tokens', 'input_tokens_details') if provider == 'openai' else ('prompt_tokens', 'completion_tokens', 'prompt_tokens_details')
        input_tokens, output_tokens = counter(raw.get(input_key)), counter(raw.get(output_key))
        total_tokens = counter(raw.get('total_tokens'))
        detail = raw.get(detail_key)
        cached = counter(detail.get('cached_tokens')) if isinstance(detail, dict) else None
    total_source = 'provider' if total_tokens is not None else 'unknown'
    consistent = not (cached is not None and (input_tokens is None or cached > input_tokens))
    if not consistent:
        cached = None
    if input_tokens is not None and output_tokens is not None:
        if total_tokens is None:
            total_tokens = counter(input_tokens + output_tokens)
            total_source = 'derived_from_provider' if total_tokens is not None else 'unknown'
            consistent = consistent and total_tokens is not None
        elif total_tokens != input_tokens + output_tokens:
            total_tokens, total_source, consistent = None, 'unknown', False
    cost = {'currency': 'USD', 'estimated_amount': None, 'pricing_version': None,
            'status': 'not_applicable' if provider == 'ollama' else 'unknown'}
    price = _prices().get((provider, model))
    if price and consistent and input_tokens is not None and output_tokens is not None and cached is not None and data.get('service_tier', 'default') == 'default':
        amount = ((input_tokens - cached) * price['input'] + cached * price['cached_input'] + output_tokens * price['output']) / 1_000_000
        try:
            amount_to_nanos(amount)
        except ValueError:
            pass
        else:
            cost.update(estimated_amount=float(amount), pricing_version=price['version'], status='estimated',
                        source=price['source'], verified_at=price['verified_at'])
    return {'provider': provider, 'model': model,
            'recorded_at': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            'latency_ms': safe_latency(latency_ms),
            'input_tokens': input_tokens, 'output_tokens': output_tokens, 'total_tokens': total_tokens,
            'cached_input_tokens': cached, 'total_tokens_source': total_source,
            'cost': cost}
