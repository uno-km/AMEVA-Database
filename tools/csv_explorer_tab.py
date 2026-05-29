"""
csv_explorer_tab.py
-------------------
CSV file explorer across all projects in the workspace.

Features:
  - Workspace-wide scan for .csv files
  - Multi-encoding detection (utf-8-sig, cp949, euc-kr, latin-1)
  - Display CSV as a sortable Treeview grid (up to 5000 rows)
  - Column header click-to-sort (ascending / descending toggle)
  - Quick-search row filter (client-side, no re-read)
  - File metadata panel (row count, column count, size, encoding)
  - Export current view back to CSV
"""
import csv
import io
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
import datetime

from tools.workspace_scanner import WorkspaceScanner

ENCODINGS = ["utf-8-sig", "utf-8", "cp949", "euc-kr", "latin-1"]
MAX_ROWS = 5000


def _detect_and_read(path: Path) -> Tuple[List[List[str]], str]:
    """Try multiple encodings; return (rows_as_list, detected_encoding)."""
    for enc in ENCODINGS:
        try:
            text = path.read_text(encoding=enc, errors="strict")
            reader = csv.reader(io.StringIO(text))
            rows = [r for r in reader]
            return rows, enc
        except (UnicodeDecodeError, LookupError):
            continue
    # Fallback
    text = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader]
    return rows, "utf-8 (replace)"


class CSVExplorerTab(ttk.Frame):
    """
    Workspace-wide CSV file explorer.

    Layout
    ------
    Left panel  : file list (path, size, modified)
    Right top   : Treeview grid of CSV contents
    Right bottom: metadata bar + search + export
    """

    def __init__(self, parent, scanner: WorkspaceScanner, status_set: Callable[[str], None]):
        super().__init__(parent)
        self._scanner = scanner
        self._status_set = status_set
        self._csv_files: Dict[str, Path] = {}
        self._current_path: Optional[Path] = None
        self._all_rows: List[List[str]] = []   # header-excluded data rows
        self._headers: List[str] = []
        self._sort_col: Optional[str] = None
        self._sort_asc: bool = True

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

        ttk.Label(left, text="CSV Files", font=("Arial", 11, "bold")).pack(
            anchor=tk.W, padx=4, pady=(4, 0)
        )
        lf = ttk.Frame(left)
        lf.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        vsb = ttk.Scrollbar(lf)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        cols = ("name", "size", "modified")
        self._file_tree = ttk.Treeview(lf, columns=cols, show="headings", yscrollcommand=vsb.set)
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

        # --- Right pane ---
        right_paned = ttk.PanedWindow(paned, orient=tk.VERTICAL)
        paned.add(right_paned, weight=4)

        # Grid
        grid_outer = ttk.Frame(right_paned)
        right_paned.add(grid_outer, weight=5)

        vsb2 = ttk.Scrollbar(grid_outer)
        vsb2.pack(side=tk.RIGHT, fill=tk.Y)
        hsb2 = ttk.Scrollbar(grid_outer, orient=tk.HORIZONTAL)
        hsb2.pack(side=tk.BOTTOM, fill=tk.X)

        self._grid = ttk.Treeview(
            grid_outer,
            yscrollcommand=vsb2.set,
            xscrollcommand=hsb2.set,
            show="headings",
        )
        self._grid.pack(fill=tk.BOTH, expand=True)
        vsb2.config(command=self._grid.yview)
        hsb2.config(command=self._grid.xview)

        # Bottom toolbar
        toolbar = ttk.Frame(right_paned)
        right_paned.add(toolbar, weight=0)

        self._meta_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self._meta_var, font=("Arial", 9)).pack(
            side=tk.LEFT, padx=8, pady=4
        )

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(toolbar, text="Filter rows:").pack(side=tk.LEFT)
        self._filter_var = tk.StringVar()
        filter_entry = ttk.Entry(toolbar, textvariable=self._filter_var, width=22)
        filter_entry.pack(side=tk.LEFT, padx=4)
        filter_entry.bind("<Return>", lambda e: self._apply_filter())
        ttk.Button(toolbar, text="Apply", command=self._apply_filter).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Clear", command=self._clear_filter).pack(side=tk.LEFT, padx=2)

        ttk.Button(toolbar, text="Export CSV", command=self._export).pack(side=tk.RIGHT, padx=8)

    # ------------------------------------------------------------------
    # Public callbacks
    # ------------------------------------------------------------------

    def on_workspace_changed(self) -> None:
        """Rescan workspace and rebuild the file list."""
        self._csv_files = self._scanner.scan_csvs()
        self._file_tree.delete(*self._file_tree.get_children())

        for display_name, path in self._csv_files.items():
            try:
                stat = path.stat()
                size_str = self._scanner.get_file_size_str(path)
                mod = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                size_str, mod = "?", "?"
            self._file_tree.insert("", tk.END, iid=display_name,
                                   values=(display_name, size_str, mod))

        self._status_set(f"Found {len(self._csv_files)} CSV file(s)")

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------

    def _on_file_select(self, _event) -> None:
        sel = self._file_tree.selection()
        if not sel:
            return
        display_name = sel[0]
        self._current_path = self._csv_files.get(display_name)
        self._load_csv()

    def _load_csv(self) -> None:
        if not self._current_path:
            return
        try:
            all_rows, encoding = _detect_and_read(self._current_path)
        except Exception as exc:
            messagebox.showerror("Read Error", f"Cannot read CSV:\n{exc}")
            return

        if not all_rows:
            self._meta_var.set("Empty file.")
            return

        header = all_rows[0]
        data = all_rows[1: MAX_ROWS + 1]

        self._headers = header
        self._all_rows = data

        self._populate_grid(header, data)

        total_rows = len(all_rows) - 1
        self._meta_var.set(
            f"{total_rows} rows  x  {len(header)} cols  |  "
            f"Encoding: {encoding}  |  Showing: {min(total_rows, MAX_ROWS)}"
        )
        self._status_set(f"Loaded {self._current_path.name}")

    def _populate_grid(self, headers: List[str], rows: List[List[str]]) -> None:
        self._grid.delete(*self._grid.get_children())
        self._grid["columns"] = headers

        for col in headers:
            self._grid.heading(
                col, text=col, anchor=tk.W,
                command=lambda c=col: self._sort_by(c)
            )
            self._grid.column(col, width=120, anchor=tk.W, stretch=True)

        for row in rows:
            # Pad short rows
            padded = row + [""] * max(0, len(headers) - len(row))
            self._grid.insert("", tk.END, values=padded[: len(headers)])

    # ------------------------------------------------------------------
    # Sort
    # ------------------------------------------------------------------

    def _sort_by(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        try:
            col_idx = self._headers.index(col)
        except ValueError:
            return

        def sort_key(row):
            val = row[col_idx] if col_idx < len(row) else ""
            try:
                return (0, float(val))
            except (ValueError, TypeError):
                return (1, str(val).lower())

        self._all_rows.sort(key=sort_key, reverse=not self._sort_asc)
        self._populate_grid(self._headers, self._all_rows)

    # ------------------------------------------------------------------
    # Filter
    # ------------------------------------------------------------------

    def _apply_filter(self) -> None:
        term = self._filter_var.get().strip().lower()
        if not term:
            self._populate_grid(self._headers, self._all_rows)
            return
        filtered = [r for r in self._all_rows if any(term in str(c).lower() for c in r)]
        self._populate_grid(self._headers, filtered)
        self._meta_var.set(f"Filter: '{term}'  |  {len(filtered)} matching row(s)")

    def _clear_filter(self) -> None:
        self._filter_var.set("")
        self._populate_grid(self._headers, self._all_rows)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export(self) -> None:
        if not self._headers:
            messagebox.showwarning("Warning", "No data to export.")
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
        )
        if not dest:
            return
        visible_rows: List[List[str]] = []
        for iid in self._grid.get_children():
            visible_rows.append(list(self._grid.item(iid)["values"]))
        try:
            with open(dest, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(self._headers)
                writer.writerows(visible_rows)
            messagebox.showinfo("Exported", f"Saved {len(visible_rows)} rows to:\n{dest}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))
