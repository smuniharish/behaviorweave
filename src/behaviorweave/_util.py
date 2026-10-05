"""Internal helpers shared across BehaviorWeave modules. Not part of the public API."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from datetime import date, datetime, time
from typing import Any


class FrozenMap[V](Mapping[str, V]):
    """Immutable, picklable, string-keyed mapping used for snapshot fields."""

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, V] | Iterable[tuple[str, V]] = ()) -> None:
        self._data: dict[str, V] = dict(data)

    def __getitem__(self, key: str) -> V:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return repr(self._data)


EMPTY_MAP: FrozenMap[Any] = FrozenMap()


def freeze[V](data: Mapping[str, V]) -> FrozenMap[V]:
    """Return ``data`` as a `FrozenMap`, reusing it when it already is one."""
    if isinstance(data, FrozenMap):
        return data
    return FrozenMap(data) if data else EMPTY_MAP


def canonical(value: object) -> Any:
    """Return a deterministic, JSON-serializable representation of ``value``.

    Mapping keys become strings, sets are sorted, tuples become lists, temporal values use ISO
    8601, Pydantic models are dumped, and any other object falls back to ``str``.
    """
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, Mapping):
        return {_key(key): canonical(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [canonical(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted((canonical(item) for item in value), key=dumps)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return canonical(model_dump(mode="json"))
    return str(value)


def dumps(value: object) -> str:
    """Serialize an already-canonical value to compact, key-sorted JSON."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _key(key: object) -> str:
    return key if isinstance(key, str) else f"<{type(key).__name__}>{key!r}"
