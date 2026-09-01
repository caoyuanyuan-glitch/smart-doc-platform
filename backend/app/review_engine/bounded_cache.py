"""Thread-safe in-process TTL/LRU cache for review acceleration."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import threading
import time


class BoundedTTLCache:
    def __init__(self, max_items: int = 1000, ttl_seconds: int = 86400, max_bytes: int = 0):
        self.max_items = max(1, int(max_items or 1))
        self.ttl_seconds = max(1, int(ttl_seconds or 1))
        self.max_bytes = max(0, int(max_bytes or 0))
        self._lock = threading.RLock()
        self._items: OrderedDict = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0

    def _expired(self, entry: dict, now: float) -> bool:
        return now - entry["ts"] > self.ttl_seconds

    def _evict_expired(self, now: float) -> None:
        for key in list(self._items):
            if self._expired(self._items[key], now):
                self._items.pop(key, None)
                self.expirations += 1

    def _evict_overflow(self) -> None:
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)
            self.evictions += 1
        if self.max_bytes:
            total = sum(int(entry.get("nbytes") or 0) for entry in self._items.values())
            while total > self.max_bytes and self._items:
                _, removed = self._items.popitem(last=False)
                total -= int(removed.get("nbytes") or 0)
                self.evictions += 1

    def _nbytes(self, value) -> int:
        try:
            return len(repr(value).encode("utf-8", errors="ignore"))
        except Exception:
            return 1

    def get(self, key, default=None):
        now = time.time()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                self.misses += 1
                return default
            if self._expired(entry, now):
                self._items.pop(key, None)
                self.expirations += 1
                self.misses += 1
                return default
            self._items.move_to_end(key)
            self.hits += 1
            return deepcopy(entry["value"])

    def set(self, key, value) -> None:
        now = time.time()
        with self._lock:
            self._evict_expired(now)
            self._items[key] = {"value": deepcopy(value), "ts": now, "nbytes": self._nbytes(value)}
            self._items.move_to_end(key)
            self._evict_overflow()

    def __setitem__(self, key, value) -> None:
        self.set(key, value)

    def __getitem__(self, key):
        value = self.get(key, default=None)
        if value is None and key not in self._items:
            raise KeyError(key)
        return value

    def pop(self, key, default=None):
        with self._lock:
            entry = self._items.pop(key, None)
            if entry is None:
                return default
            return deepcopy(entry["value"])

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def stats(self) -> dict:
        with self._lock:
            return {
                "size": len(self._items),
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "expirations": self.expirations,
                "max_items": self.max_items,
                "ttl_seconds": self.ttl_seconds,
            }
