import bisect
import difflib
import re
import sqlite3
from dataclasses import dataclass

try:
    from rapidfuzz import fuzz, process
except ImportError:
    fuzz = process = None

_WORD = re.compile(r"[^\W_]+", re.UNICODE)

_TERMS_SQL = """
SELECT e.name, e.id, c.id, c.label, c.color, 'name', e.name
FROM entries e JOIN collections c ON c.id = e.collection_id
WHERE e.deleted_at IS NULL AND c.deleted_at IS NULL
UNION ALL
SELECT a.alias, e.id, c.id, c.label, c.color, 'alias', e.name
FROM aliases a
JOIN entries e ON e.id = a.entry_id
JOIN collections c ON c.id = e.collection_id
WHERE e.deleted_at IS NULL AND c.deleted_at IS NULL
"""


@dataclass(frozen=True)
class Term:
    text: str
    entry_id: int
    collection_id: int
    collection_label: str
    color: str | None
    kind: str
    entry_name: str


class TermIndex:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._terms: list[Term] = []
        self._keys: list[str] = []
        self._word_keys: list[tuple[str, int]] = []
        self._exact: dict[str, list[int]] = {}
        self.version = 0
        self.refresh()

    def __len__(self) -> int:
        return len(self._terms)

    def refresh(self) -> None:
        rows = self._conn.execute(_TERMS_SQL).fetchall()
        terms = sorted((Term(*row) for row in rows), key=lambda t: (t.text.casefold(), t.text))
        self._terms = terms
        self._keys = [term.text.casefold() for term in terms]
        self._exact = {}
        words = []
        for index, key in enumerate(self._keys):
            self._exact.setdefault(key, []).append(index)
            for match in _WORD.finditer(key):
                words.append((match.group(), index))
        self._word_keys = sorted(words)
        self.version += 1

    def all_terms(self) -> list[Term]:
        return list(self._terms)

    def lookup(self, text: str) -> list[Term]:
        return [self._terms[i] for i in self._exact.get(text.strip().casefold(), [])]

    def prefix(self, query: str, limit: int = 10) -> list[Term]:
        key = query.strip().casefold()
        if not key:
            return []
        start = bisect.bisect_left(self._keys, key)
        found = []
        while start < len(self._keys) and self._keys[start].startswith(key):
            found.append(self._terms[start])
            start += 1
        found.sort(key=lambda t: (len(t.text), t.text.casefold()))
        return found[:limit]

    def word_prefix(self, query: str, limit: int = 10) -> list[Term]:
        key = query.strip().casefold()
        if not key:
            return []
        start = bisect.bisect_left(self._word_keys, (key, -1))
        seen, found = set(), []
        while start < len(self._word_keys) and self._word_keys[start][0].startswith(key):
            index = self._word_keys[start][1]
            if index not in seen:
                seen.add(index)
                found.append(self._terms[index])
            start += 1
        found.sort(key=lambda t: (len(t.text), t.text.casefold()))
        return found[:limit]

    def fuzzy(self, query: str, limit: int = 5, cutoff: float = 0.72) -> list[Term]:
        key = query.strip().casefold()
        if len(key) < 3 or not self._keys:
            return []
        if process is not None:
            hits = process.extract(
                key, self._keys, scorer=fuzz.WRatio, limit=limit * 3,
                score_cutoff=cutoff * 100)
            indices = [hit[2] for hit in hits]
        else:
            close = difflib.get_close_matches(key, set(self._keys), n=limit * 3, cutoff=cutoff)
            indices = [i for match in close for i in self._exact[match]]
        return [self._terms[i] for i in indices][:limit]

    def search(self, query: str, limit: int = 8) -> list[Term]:
        results: list[Term] = []
        seen_entries: set[int] = set()

        def add(terms):
            for term in terms:
                if term.entry_id not in seen_entries and len(results) < limit:
                    seen_entries.add(term.entry_id)
                    results.append(term)

        add(self.prefix(query, limit * 2))
        add(self.word_prefix(query, limit * 2))
        if len(results) < limit:
            add(self.fuzzy(query, limit))
        return results
