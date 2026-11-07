"""Server-owned configuration shared by HTTP endpoints and the AI service."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _model_for(provider: str) -> str:
    # An explicitly empty provider-specific value disables that provider. Never
    # give OpenAI the Ollama default merely because AI_MODEL was not configured.
    specific = {'openai': 'OPENAI_MODEL', 'ollama': 'OLLAMA_MODEL'}.get(provider)
    if specific and specific in os.environ:
        return os.environ[specific].strip()
    return os.getenv('AI_MODEL', 'qwen2.5:7b' if provider == 'ollama' else '').strip()


def _environment() -> str:
    current = os.getenv('APP_ENV', '').strip().lower()
    legacy = os.getenv('TEXTLAB_ENV', '').strip().lower()
    # An example .env must never downgrade a production deployment setting.
    if current and legacy and current != legacy:
        raise ValueError('APP_ENV and TEXTLAB_ENV conflict; set both to the same environment or remove one')
    return current or legacy or 'development'


@dataclass
class Settings:
    provider: str = field(default_factory=lambda: os.getenv('AI_PROVIDER', 'ollama'))
    model: str | None = None
    ollama_url: str = field(default_factory=lambda: os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434'))
    openai_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', ''), repr=False)
    app_token: str = field(default_factory=lambda: os.getenv('TEXTLAB_TOKEN', ''), repr=False)
    environment: str = field(default_factory=_environment)
    allowed_hosts: tuple[str, ...] = field(default_factory=lambda: tuple(os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost,testserver').split(',')))
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: tuple(os.getenv('ALLOWED_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8767,http://localhost:8767').split(',')))
    requests_per_minute: int = field(default_factory=lambda: int(os.getenv('TEXTLAB_REQUESTS_PER_MINUTE', '20')))
    auth_mode: str = field(default_factory=lambda: os.getenv('TEXTLAB_AUTH_MODE', 'private'))
    user_token_hashes: dict[str, str] = field(default_factory=lambda: json.loads(os.getenv('TEXTLAB_USER_TOKENS', '{}')), repr=False)
    state_db: str = field(default_factory=lambda: os.getenv('TEXTLAB_STATE_DB', ''))
    compatible_url: str = field(default_factory=lambda: os.getenv('AI_COMPATIBLE_URL', ''))
    compatible_key: str = field(default_factory=lambda: os.getenv('AI_COMPATIBLE_KEY', ''), repr=False)
    ollama_think: bool | None = field(default_factory=lambda: {'false': False, 'true': True, 'default': None}[os.getenv('OLLAMA_THINK', 'false').lower()])
    max_concurrent: int = field(default_factory=lambda: int(os.getenv('TEXTLAB_MAX_CONCURRENT', '2')))
    daily_token_budget: int = field(default_factory=lambda: int(os.getenv('TEXTLAB_DAILY_TOKEN_BUDGET', '250000')))
    global_daily_token_budget: int = field(default_factory=lambda: int(os.getenv('TEXTLAB_GLOBAL_DAILY_TOKEN_BUDGET', '1000000')))
    max_output_tokens: int = field(default_factory=lambda: int(os.getenv('TEXTLAB_MAX_OUTPUT_TOKENS', '6000')))
    max_body_bytes: int = 100000
    max_provider_bytes: int = 200000
    request_timeout: float = field(default_factory=lambda: float(os.getenv('AI_REQUEST_TIMEOUT', os.getenv('TEXTLAB_REQUEST_TIMEOUT', '120'))))
    body_timeout: float = 10
    readiness_timeout: float = 15
    max_input_chars: int = field(default_factory=lambda: int(os.getenv('AI_MAX_INPUT_CHARS', '8000')))
    # Only successful, non-generating model metadata checks are cached. The
    # credential is represented by a digest; raw credentials are never retained
    # in cache keys, exceptions or diagnostics.
    _openai_model_cache: dict[tuple[str, str], float] = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.provider = self.provider.strip().lower()
        self.environment = self.environment.strip().lower()
        if self.environment not in ('development', 'production', 'test'):
            raise ValueError('Invalid environment: APP_ENV/TEXTLAB_ENV must be development, production or test')
        self.model = _model_for(self.provider) if self.model is None else self.model.strip()
        self.openai_key = self.openai_key.strip()
        self.compatible_key = self.compatible_key.strip()
        if not isinstance(self.max_input_chars, int) or isinstance(self.max_input_chars, bool) or not 10 <= self.max_input_chars <= 8000:
            raise ValueError('AI_MAX_INPUT_CHARS must be an integer between 10 and 8000')
