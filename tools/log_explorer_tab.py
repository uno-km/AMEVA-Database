"""
log_explorer_tab.py
-------------------
Log file explorer across all projects in the workspace.

Features:
  - Workspace-wide scan for .log files (excludes venv, .git, etc.)
  - File size and last-modified display
  - Content viewer with multi-encoding fallback (utf-8, cp949, euc-kr)
  - Real-time search / highlight within log content
  - Level filter: ALL | INFO | WARNING | ERROR
  - Live-tail mode: auto-refreshes the current file every N seconds
  - Rescan button to pick up newly created log files
"""
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Dict, Optional
import datetime
import threading

from tools.workspace_scanner import WorkspaceScanner

ENCODINGS = ["utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"]
LEVEL_COLORS = {
    "ERROR":   "#B71C1C",
    "WARNING": "#E65100",
    "WARN":    "#E65100",
    "INFO":    "#1B5E20",
    "DEBUG":   "#616161",
}


def _read_file(path: Path) -> str:
    for enc in ENCODINGS:
        try:
            return path.read_text(encoding=enc, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


class LogExplorerTab(ttk.Frame):
    """
    Workspace-wide log file explorer with live-tail and search.

    Layout
    ------
    Left panel   : file list (name, size, modified)
    Right top    : log content Text widget (colour-coded by log level)
    Right bottom : filter/search toolbar + live-tail controls
    """

    TAIL_INTERVAL_MS = 2000  # refresh every 2 s in tail mode

    def __init__(self, parent, scanner: WorkspaceScanner, status_set: Callable[[str], None]):
        super().__init__(parent)
        self._scanner = scanner
        self._status_set = status_set
        self._log_files: Dict[str, Path] = {}
        self._current_path: Optional[Path] = None
        self._tail_job: Optional[str] = None  # after() handle
        self._tail_active = tk.BooleanVar(value=False)
        self._last_size: int = 0

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # --- Left: file list ---
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        ttk.Label(left, text="Log Files", font=("Arial", 11, "bold")).pack(
            anchor=tk.W, padx=4, pady=(4, 0)
        )

        cols = ("name", "size", "modified")
        lf = ttk.Frame(left)
        lf.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        vsb = ttk.Scrollbar(lf)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._file_tree = ttk.Treeview(
            lf, columns=cols, show="headings", yscrollcommand=vsb.set
        )
        vsb.config(command=self._file_tree.yview)

        self._file_tree.heading("name",     text="Path",     anchor=tk.W)
        self._file_tree.heading("size",     text="Size",     anchor=tk.W)
        self._file_tree.heading("modified", text="Modified", anchor=tk.W)
        self._file_tree.column("name",     width=200, stretch=True)
        self._file_tree.column("size",     width=60,  stretch=False)
        self._file_tree.column("modified", width=120, stretch=False)
        self._file_tree.pack(fill=tk.BOTH, expand=True)
        self._file_tree.bind("<<TreeviewSelect>>", self._on_file_select)

        ttk.Button(left, text="Rescan", command=self.on_workspace_changed).pack(
            fill=tk.X, padx=4, pady=(0, 4)
        )

        # --- Right: content + toolbar ---
        right_paned = ttk.PanedWindow(paned, orient=tk.VERTICAL)
        paned.add(right_paned, weight=4)

        # Content viewer
        content_frame = ttk.Frame(right_paned)
        right_paned.add(content_frame, weight=5)

        vsb2 = ttk.Scrollbar(content_frame)
        vsb2.pack(side=tk.RIGHT, fill=tk.Y)
        hsb2 = ttk.Scrollbar(content_frame, orient=tk.HORIZONTAL)
        hsb2.pack(side=tk.BOTTOM, fill=tk.X)

        self._content = tk.Text(
            content_frame,
            font=("Courier", 9),
            state=tk.DISABLED,
            wrap=tk.NONE,
            yscrollcommand=vsb2.set,
            xscrollcommand=hsb2.set,
        )
        self._content.pack(fill=tk.BOTH, expand=True)
        vsb2.config(command=self._content.yview)
        hsb2.config(command=self._content.xview)

        # Configure colour tags
        for level, colour in LEVEL_COLORS.items():
            self._content.tag_config(level, foreground=colour)
        self._content.tag_config("SEARCH", background="#FFF176")

        # Toolbar
        toolbar = ttk.Frame(right_paned)
        right_paned.add(toolbar, weight=0)

        ttk.Label(toolbar, text="Filter:").pack(side=tk.LEFT, padx=(6, 2))
        self._level_var = tk.StringVar(value="ALL")
        for lv in ("ALL", "INFO", "WARNING", "ERROR"):
            ttk.Radiobutton(
                toolbar, text=lv, variable=self._level_var,
                value=lv, command=self._reload_current
            ).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(toolbar, text="Search:").pack(side=tk.LEFT, padx=(0, 2))
        self._search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self._search_var, width=22)
        search_entry.pack(side=tk.LEFT, padx=2)
        search_entry.bind("<Return>", lambda e: self._search())
        ttk.Button(toolbar, text="Find", command=self._search).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Clear", command=self._clear_search).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Checkbutton(
            toolbar, text="Live Tail", variable=self._tail_active,
            command=self._toggle_tail
        ).pack(side=tk.LEFT, padx=2)

        self._line_count_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self._line_count_var, font=("Arial", 9)).pack(
            side=tk.RIGHT, padx=8
        )

    # ------------------------------------------------------------------
    # Public callbacks
    # ------------------------------------------------------------------

    def on_workspace_changed(self) -> None:
        """Rescan the workspace for log files and rebuild the file list."""
        self._log_files = self._scanner.scan_logs()
        self._file_tree.delete(*self._file_tree.get_children())

        for display_name, path in self._log_files.items():
            try:
                stat = path.stat()
                size_str = self._scanner.get_file_size_str(path)
                mod = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                size_str, mod = "?", "?"
            self._file_tree.insert("", tk.END, iid=display_name,
                                   values=(display_name, size_str, mod))

        self._status_set(f"Found {len(self._log_files)} log file(s)")

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------

    def _on_file_select(self, _event) -> None:
        sel = self._file_tree.selection()
        if not sel:
            return
        display_name = sel[0]
        self._current_path = self._log_files.get(display_name)
        self._last_size = 0
        self._reload_current()
        if self._tail_active.get():
            self._stop_tail()
            self._start_tail()

    def _reload_current(self) -> None:
        if not self._current_path:
            return
        try:
            text = _read_file(self._current_path)
        except Exception as exc:
            messagebox.showerror("Read Error", str(exc))
            return

        level_filter = self._level_var.get()
        lines = text.splitlines()
        if level_filter != "ALL":
            lines = [l for l in lines if level_filter in l.upper()]

        self._set_content("\n".join(lines))
        self._line_count_var.set(f"{len(lines)} line(s)")
        self._last_size = self._current_path.stat().st_size if self._current_path.exists() else 0

    # ------------------------------------------------------------------
    # Content display
    # ------------------------------------------------------------------

    def _set_content(self, text: str) -> None:
        self._content.config(state=tk.NORMAL)
        self._content.delete("1.0", tk.END)

        for line in text.splitlines(keepends=True):
            # Determine which colour tag to apply
            tag = None
            upper = line.upper()
            for level in ("ERROR", "WARNING", "WARN", "INFO", "DEBUG"):
                if level in upper:
                    tag = level
                    break
            if tag:
                self._content.insert(tk.END, line, (tag,))
            else:
                self._content.insert(tk.END, line)

        # Auto-scroll to bottom
        self._content.see(tk.END)
        self._content.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _search(self) -> None:
        self._content.tag_remove("SEARCH", "1.0", tk.END)
        term = self._search_var.get().strip()
        if not term:
            return
        start = "1.0"
        count = 0
        while True:
            pos = self._content.search(term, start, stopindex=tk.END, nocase=True)
            if not pos:
                break
            end = f"{pos}+{len(term)}c"
            self._content.tag_add("SEARCH", pos, end)
            start = end
            count += 1

        if count:
            # Scroll to first match
            first = self._content.tag_ranges("SEARCH")
            if first:
                self._content.see(first[0])
        self._line_count_var.set(f"{count} match(es) found")

    def _clear_search(self) -> None:
        self._search_var.set("")
        self._content.tag_remove("SEARCH", "1.0", tk.END)

    # ------------------------------------------------------------------
    # Live tail
    # ------------------------------------------------------------------

    def _toggle_tail(self) -> None:
        if self._tail_active.get():
            self._start_tail()
        else:
            self._stop_tail()

    def _start_tail(self) -> None:
        self._tail_job = self.after(self.TAIL_INTERVAL_MS, self._tail_tick)

    def _stop_tail(self) -> None:
        if self._tail_job:
            self.after_cancel(self._tail_job)
            self._tail_job = None

    def _tail_tick(self) -> None:
        if not self._current_path or not self._current_path.exists():
            return
        try:
            new_size = self._current_path.stat().st_size
        except OSError:
            return

        if new_size != self._last_size:
            self._reload_current()

        if self._tail_active.get():
            self._tail_job = self.after(self.TAIL_INTERVAL_MS, self._tail_tick)
