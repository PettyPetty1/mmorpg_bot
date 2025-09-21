
from __future__ import annotations
from importlib import import_module
class Registry:
    def __init__(self):
        self._map: dict[str, str] = {}
    def register(self, key: str, target: str) -> None:
        self._map[key] = target
    def target(self, key: str) -> str:
        return self._map.get(key, key)
    def create(self, key: str, *args, **kwargs):
        target = self.target(key)
        mod_path, _, obj = target.partition(":")
        mod = import_module(mod_path)
        cls = getattr(mod, obj) if obj else mod
        return cls(*args, **kwargs)
REGISTRY = Registry()
