"""SQLite cache manager for verification queries and CVF conference proceedings ToC."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Literal

from rapidfuzz import fuzz

from bibcanon.config import get_cache_db_path
from bibcanon.models import ExtractedEntryFeatures


class BibCache:
    """Thread-safe local SQLite cache storing query results and CVF ToC entries."""

    def __init__(self, db_path: Path | None = None, ttl_days: int = 30) -> None:
        self.db_path = Path(db_path) if db_path is not None else get_cache_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = max(1, ttl_days) * 86400
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cvf_toc_cache (
                    venue TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    norm_title TEXT NOT NULL,
                    raw_title TEXT NOT NULL,
                    paper_url TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (venue, year, norm_title)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cvf_toc_meta (
                    venue TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    entry_count INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (venue, year)
                )
                """
            )
            conn.commit()

    @staticmethod
    def build_query_key(features: ExtractedEntryFeatures, override_title: str | None = None) -> str:
        """Build deterministic cache key capturing entry identity & venue intent."""
        key_payload = {
            "norm_title": (override_title or features.normalized_title).strip(),
            "surnames": features.author_surnames[:5],
            "has_et_al": features.has_et_al,
            "year": features.year,
            "venue_id": features.canonical_venue_id,
            "raw_venue": (features.raw_venue or "").strip().lower(),
            "doi": (features.doi or "").strip().lower(),
            "arxiv_id": (features.arxiv_id or "").strip().lower(),
            "is_preprint": features.is_preprint,
        }
        serialized = json.dumps(key_payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get_query_result(
        self, cache_key: str, ttl_days: int | None = None
    ) -> dict[str, Any] | None:
        """Retrieve cached verification payload if present and not expired."""
        ttl = (ttl_days * 86400) if ttl_days is not None else self.ttl_seconds
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, created_at FROM query_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if not row:
                return None
            if now - float(row["created_at"]) > ttl:
                conn.execute("DELETE FROM query_cache WHERE cache_key = ?", (cache_key,))
                conn.commit()
                return None
            try:
                return json.loads(row["payload_json"])
            except Exception:
                return None

    def set_query_result(self, cache_key: str, payload: dict[str, Any]) -> None:
        """Store verification payload in query_cache."""
        serialized = json.dumps(payload, ensure_ascii=False)
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO query_cache (cache_key, payload_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (cache_key, serialized, now),
            )
            conn.commit()

    def has_cvf_toc(self, venue: str, year: int, ttl_days: int | None = None) -> bool:
        """Return True if the full CVF proceedings ToC for (venue, year) is cached and fresh."""
        ttl = (ttl_days * 86400) if ttl_days is not None else self.ttl_seconds
        now = time.time()
        v_up = venue.upper()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT created_at, entry_count FROM cvf_toc_meta WHERE venue = ? AND year = ?",
                (v_up, year),
            ).fetchone()
            if not row:
                return False
            if now - float(row["created_at"]) > ttl or int(row["entry_count"]) == 0:
                return False
            return True

    def save_cvf_toc(
        self,
        venue: str,
        year: int,
        entries: list[tuple[str, str, str]],
    ) -> None:
        """Persist parsed CVF proceedings ToC entries (norm_title, raw_title, paper_url)."""
        v_up = venue.upper()
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM cvf_toc_cache WHERE venue = ? AND year = ?",
                (v_up, year),
            )
            conn.executemany(
                """
                INSERT OR REPLACE INTO cvf_toc_cache
                (venue, year, norm_title, raw_title, paper_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(v_up, year, nt, rt, url, now) for nt, rt, url in entries if nt and url],
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO cvf_toc_meta (venue, year, entry_count, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (v_up, year, len(entries), now),
            )
            conn.commit()

    def lookup_cvf_paper_url(
        self, venue: str, year: int, norm_title: str
    ) -> str | None:
        """Find a CVF paper detail page URL from cached ToC by exact or >=95 fuzzy title."""
        if not norm_title:
            return None
        v_up = venue.upper()
        with self._connect() as conn:
            exact = conn.execute(
                """
                SELECT paper_url FROM cvf_toc_cache
                WHERE venue = ? AND year = ? AND norm_title = ?
                """,
                (v_up, year, norm_title),
            ).fetchone()
            if exact:
                return str(exact["paper_url"])

            # High-precision fuzzy fallback for minor punctuation/hyphen variations
            rows = conn.execute(
                "SELECT norm_title, paper_url FROM cvf_toc_cache WHERE venue = ? AND year = ?",
                (v_up, year),
            ).fetchall()

        best_url: str | None = None
        best_ratio = 0.0
        for row in rows:
            r = fuzz.ratio(norm_title, str(row["norm_title"]))
            if r >= 95.0 and r > best_ratio:
                best_ratio = r
                best_url = str(row["paper_url"])
        return best_url

    def get_stats(self) -> dict[str, Any]:
        """Return cache row statistics and file size."""
        with self._connect() as conn:
            q_count = conn.execute("SELECT COUNT(*) AS c FROM query_cache").fetchone()["c"]
            toc_venues = conn.execute("SELECT COUNT(*) AS c FROM cvf_toc_meta").fetchone()["c"]
            toc_papers = conn.execute("SELECT COUNT(*) AS c FROM cvf_toc_cache").fetchone()["c"]
        size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {
            "db_path": str(self.db_path),
            "db_size_bytes": size_bytes,
            "query_cache_count": int(q_count),
            "cvf_toc_venues_count": int(toc_venues),
            "cvf_toc_papers_count": int(toc_papers),
        }

    def clear(self, scope: Literal["all", "queries"] = "all") -> int:
        """Clear cached entries according to scope and return total deleted rows."""
        deleted = 0
        with self._connect() as conn:
            cur1 = conn.execute("DELETE FROM query_cache")
            deleted += cur1.rowcount if cur1.rowcount and cur1.rowcount > 0 else 0
            if scope == "all":
                cur2 = conn.execute("DELETE FROM cvf_toc_cache")
                deleted += cur2.rowcount if cur2.rowcount and cur2.rowcount > 0 else 0
                conn.execute("DELETE FROM cvf_toc_meta")
            conn.commit()
        return deleted
