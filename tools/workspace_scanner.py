"""
workspace_scanner.py
--------------------
Scans a workspace directory for SQLite databases, log files, and CSV files.
Excludes known non-project directories (venv, .git, node_modules, etc.).
"""
from pathlib import Path
from typing import Dict

EXCLUDE_DIRS: frozenset = frozenset({
    "venv", ".venv", "node_modules", "__pycache__",
    ".git", ".idea", ".vscode", "dist", "build", "target", "logs",
})

DB_EXTENSIONS: frozenset = frozenset({".db", ".sqlite", ".sqlite3"})
LOG_EXTENSIONS: frozenset = frozenset({".log"})
CSV_EXTENSIONS: frozenset = frozenset({".csv"})


def _is_excluded(path: Path) -> bool:
    """Returns True if the path contains any excluded directory segment."""
    return any(part in EXCLUDE_DIRS for part in path.parts)


class WorkspaceScanner:
    """
    Recursively scans a workspace directory for files by extension.
    Maintains the workspace root and provides refresh capabilities.
    """

    def __init__(self, workspace_path: Path):
        self._workspace = Path(workspace_path).resolve()

    @property
    def workspace_path(self) -> Path:
        return self._workspace

    @workspace_path.setter
    def workspace_path(self, path: Path):
        self._workspace = Path(path).resolve()

    def _scan(self, extensions: frozenset) -> Dict[str, Path]:
        """
        Generic scan method. Returns a sorted dict of {display_name -> absolute_path}.
        """
        results: Dict[str, Path] = {}
        for ext in extensions:
            try:
                for p in self._workspace.rglob(f"*{ext}"):
                    if _is_excluded(p) or not p.is_file():
                        continue
                    try:
                        key = str(p.relative_to(self._workspace))
                    except ValueError:
                        key = str(p)
                    results[key] = p
            except PermissionError:
                continue
        return dict(sorted(results.items()))

    def scan_databases(self) -> Dict[str, Path]:
        """Scan for SQLite database files."""
        return self._scan(DB_EXTENSIONS)

    def scan_logs(self) -> Dict[str, Path]:
        """Scan for .log files (excluding the app's own logs directory)."""
        return self._scan(LOG_EXTENSIONS)

    def scan_csvs(self) -> Dict[str, Path]:
        """Scan for CSV files."""
        return self._scan(CSV_EXTENSIONS)

    def get_file_size_str(self, path: Path) -> str:
        """Returns a human-readable file size string."""
        try:
            size = path.stat().st_size
            if size < 1024:
                return f"{size} B"
            elif size < 1024 ** 2:
                return f"{size / 1024:.1f} KB"
            else:
                return f"{size / 1024 ** 2:.1f} MB"
        except OSError:
            return "? KB"
