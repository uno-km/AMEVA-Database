"""
db_manager.py
-------------
Centralized SQLite database manager.
Handles all connection lifecycle, query execution, timing, logging,
and in-memory query history for dashboard analytics.
"""
import sqlite3
import logging
import logging.handlers
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


class QueryRecord:
    """Immutable record of a single executed query and its outcome."""
    __slots__ = ("query", "elapsed_ms", "success", "rowcount", "error")

    def __init__(
        self,
        query: str,
        elapsed_ms: float,
        success: bool,
        rowcount: int,
        error: Optional[str] = None,
    ):
        self.query = query
        self.elapsed_ms = elapsed_ms
        self.success = success
        self.rowcount = rowcount
        self.error = error

    def __repr__(self) -> str:
        status = "OK" if self.success else f"ERR:{self.error}"
        return f"<QueryRecord [{status}] {self.elapsed_ms:.1f}ms rows={self.rowcount}>"


class DBManager:
    """
    Manages a single active SQLite connection context.

    Responsibilities:
    - Connection lifecycle (open-execute-close per query, never holds a lock)
    - Unified query execution with timing and structured logging
    - In-memory query history (capped at MAX_HISTORY entries)
    - Autocomplete cache (table names + column names for the active DB)
    - SQLite PRAGMA optimizations for edge device environments
    """

    MAX_HISTORY: int = 200

    def __init__(self, log_dir: Path):
        self.db_path: Optional[Path] = None
        self.logger = self._setup_logger(log_dir)
        self.all_tables: List[str] = []
        self.all_columns: set = set()
        self.query_history: deque = deque(maxlen=self.MAX_HISTORY)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_logger(self, log_dir: Path) -> logging.Logger:
        log_dir.mkdir(exist_ok=True, parents=True)
        log_file = log_dir / "db_inspector.log"
        logger = logging.getLogger("AMEVA.DBManager")
        logger.setLevel(logging.DEBUG)
        if not logger.handlers:
            fh = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=2 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)-5s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            logger.addHandler(fh)
        return logger

    # ------------------------------------------------------------------
    # Database selection
    # ------------------------------------------------------------------

    def set_database(self, db_path: Path) -> None:
        """Switch the active database and rebuild autocomplete cache."""
        self.db_path = Path(db_path)
        self.logger.info(f"Switched database -> {self.db_path}")
        self._refresh_cache()

    def clear_database(self) -> None:
        self.db_path = None
        self.all_tables = []
        self.all_columns = set()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _open(self) -> Optional[sqlite3.Connection]:
        """Open a new connection. Caller is responsible for closing it."""
        if not self.db_path:
            return None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as exc:
            self.logger.error(f"Connection failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Core query executor
    # ------------------------------------------------------------------

    def execute(
        self,
        query: str,
        params: Optional[List[Any]] = None,
        commit: bool = False,
    ) -> Tuple[bool, Optional[list], Optional[List[str]], Optional[str], int, float]:
        """
        Execute a single SQL statement.

        Returns
        -------
        (success, rows, columns, error_msg, rowcount, elapsed_ms)
        """
        if not self.db_path:
            return False, None, None, "No database selected.", 0, 0.0

        conn = self._open()
        if conn is None:
            return False, None, None, "Failed to open connection.", 0, 0.0

        start = time.perf_counter()
        try:
            cur = conn.cursor()
            cur.execute(query, params or [])
            elapsed_ms = (time.perf_counter() - start) * 1000

            if cur.description:
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                if commit:
                    conn.commit()
                self.logger.info(
                    f"DB:{self.db_path.name} | SQL:{query.strip()!r} | "
                    f"params={params} | OK | rows={len(rows)} | {elapsed_ms:.1f}ms"
                )
                self.query_history.append(
                    QueryRecord(query.strip(), elapsed_ms, True, len(rows))
                )
                return True, rows, cols, None, len(rows), elapsed_ms

            # Non-SELECT statement
            if commit:
                conn.commit()
            elapsed_ms = (time.perf_counter() - start) * 1000
            rc = cur.rowcount
            self.logger.info(
                f"DB:{self.db_path.name} | SQL:{query.strip()!r} | "
                f"params={params} | OK | affected={rc} | {elapsed_ms:.1f}ms"
            )
            self.query_history.append(
                QueryRecord(query.strip(), elapsed_ms, True, rc)
            )
            return True, None, None, None, rc, elapsed_ms

        except sqlite3.Error as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.logger.error(
                f"DB:{self.db_path.name} | SQL:{query.strip()!r} | "
                f"params={params} | ERROR:{exc} | {elapsed_ms:.1f}ms"
            )
            self.query_history.append(
                QueryRecord(query.strip(), elapsed_ms, False, 0, str(exc))
            )
            return False, None, None, str(exc), 0, elapsed_ms
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Autocomplete cache
    # ------------------------------------------------------------------

    def _refresh_cache(self) -> None:
        """Rebuild table-name and column-name lists for autocomplete."""
        self.all_tables = []
        self.all_columns = set()
        if not self.db_path:
            return
        conn = self._open()
        if conn is None:
            return
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
            )
            for row in cur.fetchall():
                name = row["name"]
                self.all_tables.append(name)
                try:
                    cur.execute(f"PRAGMA table_info({name});")
                    for col in cur.fetchall():
                        self.all_columns.add(col["name"])
                except Exception:
                    pass
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Analytics helpers (used by dashboard)
    # ------------------------------------------------------------------

    def get_table_row_counts(self) -> Dict[str, int]:
        """Return {table_name: row_count} for all tables in active DB."""
        if not self.db_path:
            return {}
        conn = self._open()
        if conn is None:
            return {}
        counts: Dict[str, int] = {}
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
            )
            tables = [r["name"] for r in cur.fetchall()]
            for t in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) AS cnt FROM {t};")
                    row = cur.fetchone()
                    counts[t] = int(row["cnt"]) if row else 0
                except Exception:
                    counts[t] = -1
        finally:
            conn.close()
        return counts

    def get_recent_query_timings(self, n: int = 30) -> List[Tuple[str, float, bool]]:
        """Return the last n (short_label, elapsed_ms, success) tuples."""
        result = []
        records = list(self.query_history)[-n:]
        for rec in records:
            label = rec.query[:20].replace("\n", " ")
            result.append((label, rec.elapsed_ms, rec.success))
        return result

    # ------------------------------------------------------------------
    # SQLite Optimization
    # ------------------------------------------------------------------

    def apply_optimizations(self) -> List[Tuple[str, bool, Optional[str]]]:
        """
        Apply recommended PRAGMAs for CPU-constrained edge device environments.
        WAL mode improves concurrent read/write without blocking AI processes.
        """
        pragmas = [
            "PRAGMA journal_mode = WAL;",
            "PRAGMA synchronous = NORMAL;",
            "PRAGMA cache_size = -8000;",
            "PRAGMA foreign_keys = ON;",
            "PRAGMA temp_store = MEMORY;",
            "PRAGMA mmap_size = 67108864;",  # 64 MB memory-mapped I/O
        ]
        results = []
        for pragma in pragmas:
            res = self.execute(pragma)
            success, error = res[0], res[3]
            results.append((pragma, success, error))
        return results
