"""Validated API and model contracts shared across the AI service."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


def utf16_length(value: str) -> int:
    """Match JavaScript string limits and reject invalid Unicode surrogate data."""
    return len(value.encode('utf-16-le')) // 2


class RewriteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=8000)
    tone: Literal['natural','simple','professional','academic','concise','detailed'] = 'natural'
    language: Literal['sv','en'] = 'sv'
    protected_terms: list[str] = Field(default_factory=list, max_length=40)

    @field_validator('protected_terms')
    @classmethod
    def valid_terms(cls, values: list[str]) -> list[str]:
        if any(not term.strip() or utf16_length(term) > 160 for term in values):
            raise ValueError('Invalid protected terms')
        return list(dict.fromkeys(values))

    @field_validator('text')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if utf16_length(value.strip()) < 10 or utf16_length(value) > 8000:
            raise ValueError('Text must contain 10 to 8000 UTF-16 units')
        return value

class ModelText(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=16000)

    @field_validator('text')
    @classmethod
    def bounded_unicode(cls, value: str) -> str:
        if utf16_length(value) > 16000:
            raise ValueError('Output is too long')
        return value


class DetectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=12000)
    language: Literal["auto", "sv", "en"] = "auto"

    @field_validator('text')
    @classmethod
    def bounded_unicode(cls, value: str) -> str:
        if utf16_length(value) > 12000:
            raise ValueError('Input is too long')
        return value
