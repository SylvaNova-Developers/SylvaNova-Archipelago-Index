from __future__ import annotations

__all__ = ["main"]


def __getattr__(name: str):
    if name == "main":
        from .bot import main as _main

        return _main
    raise AttributeError(name)
