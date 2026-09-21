"""Shared JSON/config typing helpers for settings modules."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Mapping

type JsonObject = dict[str, object]


def is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether value is a string-keyed JSON-style object."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def object_from_mapping(value: Mapping[object, object]) -> JsonObject:
    """Return a string-keyed object from a mapping, dropping non-string keys."""
    return {key: item for key, item in value.items() if isinstance(key, str)}


def object_or_empty(value: object) -> JsonObject:
    """Return a JSON object for value, or an empty object when invalid."""
    if is_json_object(value):
        return value
    return {}


def string_value(value: object, default: str = "") -> str:
    """Return value when it is a string, otherwise default."""
    return value if isinstance(value, str) else default


def optional_string(value: object) -> str | None:
    """Return value when it is a string, otherwise None."""
    return value if isinstance(value, str) else None


def int_value(value: object, default: int = 0) -> int:
    """Return value coerced to int when it is a JSON scalar, otherwise default."""
    if isinstance(value, str | bytes | bytearray | int | float):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def bool_value(value: object, default: bool = False) -> bool:
    """Return value coerced to bool using config-friendly rules."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if isinstance(value, int | float):
        return bool(value)
    return default
