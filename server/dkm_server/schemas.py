"""Request/response shapes for the API."""

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _check_key(v: str) -> str:
    if not KEY_PATTERN.match(v):
        raise ValueError("must be lowercase letters, digits, '-' or '_'")
    return v


class VariantIn(BaseModel):
    key: str = Field(max_length=100)
    weight: float = Field(default=1.0, gt=0)
    config: dict[str, Any] = Field(default_factory=dict)

    _k = field_validator("key")(_check_key)


class VariantOut(VariantIn):
    pass


class ExperimentIn(BaseModel):
    key: str = Field(max_length=100)
    name: str = Field(max_length=200)
    description: str = ""
    primary_metric: str | None = None
    variants: list[VariantIn] = Field(min_length=2)

    _k = field_validator("key")(_check_key)

    @field_validator("variants")
    @classmethod
    def unique_variant_keys(cls, v: list[VariantIn]) -> list[VariantIn]:
        keys = [x.key for x in v]
        if len(keys) != len(set(keys)):
            raise ValueError("variant keys must be unique")
        return v


class ExperimentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    primary_metric: str | None = None
    status: Literal["draft", "running", "stopped"] | None = None


class ExperimentOut(BaseModel):
    key: str
    name: str
    description: str
    status: str
    primary_metric: str | None
    created_at: datetime
    variants: list[VariantOut]
    event_count: int = 0


class EventIn(BaseModel):
    experiment: str
    variant: str
    user_id: str = Field(max_length=200)
    metric: str = Field(max_length=100)
    value: float
    timestamp: datetime | None = None


class EventBatch(BaseModel):
    events: list[EventIn] = Field(max_length=1000)


class IngestResult(BaseModel):
    accepted: int
    rejected: int
