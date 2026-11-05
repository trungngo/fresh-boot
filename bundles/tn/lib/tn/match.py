"""Name matching shared by ``tn sessions attach`` and plugins (``tn claude attach``, ...)."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Sequence


def match(query: str | None, items: Sequence[Any],
          keys: Callable[[Any], Iterable[str | None]]) -> list:
    """The items whose keys match ``query`` case-insensitively, best tier only: exact, then
    prefix, then substring. No query: every item. No match: []."""
    items = list(items)
    if not query:
        return items
    q = query.lower()
    tiers: list[list] = [[], [], []]
    for it in items:
        ks = [k.lower() for k in keys(it) if k]
        if any(k == q for k in ks):
            tiers[0].append(it)
        elif any(k.startswith(q) for k in ks):
            tiers[1].append(it)
        elif any(q in k for k in ks):
            tiers[2].append(it)
    for t in tiers:
        if t:
            return t
    return []


def subsequence(q: str, text: str) -> bool:
    """Whether the characters of ``q`` appear in ``text`` in order (case-insensitive)."""
    it = iter(text.lower())
    return all(c in it for c in q.lower())
