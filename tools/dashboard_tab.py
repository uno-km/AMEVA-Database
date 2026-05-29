"""
dashboard_tab.py
----------------
Live analytics dashboard for the AMEVA global DB inspector.

Panels
------
1. DB Row Counts     : bar chart — current row count per table in active DB
2. Query Performance : line chart — last N query execution times (ms)
3. Log Health        : bar chart — ERROR / WARNING / INFO count in all workspace logs
4. Quick Stats       : text panel — DB file size, total tables, last-query timing

Depends on matplotlib (optional). If not installed, a fallback message is shown.
Auto-refresh is implemented with tk.after() on the main thread — no threads needed.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Dict, List, Optional

from tools.db_manager import DBManager
from tools.workspace_scanner import WorkspaceScanner

ENCODINGS = ["utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"]

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.ticker as ticker
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def _count_log_levels(scanner: WorkspaceScanner) -> Dict[str, int]:
    """Scan all log files and count ERROR / WARNING / INFO lines."""
    counts = {"ERROR": 0, "WARNING": 0, "INFO": 0}
    log_files = scanner.scan_logs()
    for path in log_files.values():
        for enc in ENCODINGS:
            try:
                text = path.read_text(encoding=enc, errors="strict")
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
        for line in text.splitlines():
            upper = line.upper()
            if "ERROR" in upper:
                counts["ERROR"] += 1
            elif "WARNING" in upper or "WARN" in upper:
                counts["WARNING"] += 1
            elif "INFO" in upper:
                counts["INFO"] += 1
    return counts


class DashboardTab(ttk.Frame):
    """
    Live analytics dashboard.

    Parameters
    ----------
    db_manager : DBManager
    scanner    : WorkspaceScanner
    status_set : callable  — writes to the bottom status bar
    """

    REFRESH_INTERVAL_MS = 5000  # 5 seconds default

    def __init__(
        self,
        parent,
        db_manager: DBManager,
        scanner: WorkspaceScanner,
        status_set: Callable[[str], None],
    ):
        super().__init__(parent)
        self.db = db_manager
        self._scanner = scanner
        self._status_set = status_set
        self._auto_job: Optional[str] = None
        self._auto_active = tk.BooleanVar(value=False)
        self._interval_var = tk.IntVar(value=5)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Toolbar
        tb = ttk.Frame(self)
        tb.pack(fill=tk.X, padx=6, pady=4)

        ttk.Button(tb, text="Refresh Now", command=self.refresh).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(
            tb, text="Auto-Refresh", variable=self._auto_active,
            command=self._toggle_auto
        ).pack(side=tk.LEFT, padx=6)
        ttk.Label(tb, text="Interval (s):").pack(side=tk.LEFT)
        ttk.Spinbox(tb, from_=2, to=60, textvariable=self._interval_var, width=4).pack(
            side=tk.LEFT, padx=2
        )

        self._last_refresh_var = tk.StringVar(value="Never refreshed")
        ttk.Label(tb, textvariable=self._last_refresh_var, font=("Arial", 9)).pack(
            side=tk.RIGHT, padx=8
        )

        if not HAS_MATPLOTLIB:
            msg = (
                "matplotlib is not installed.\n\n"
                "Install it to enable charts:\n\n"
                "    pip install matplotlib\n\n"
                "The Quick Stats panel below is still available."
            )
            ttk.Label(self, text=msg, font=("Arial", 11), foreground="#B71C1C",
                      justify=tk.CENTER).pack(pady=20)
            self._build_stats_panel()
            return

        # Chart canvas area
        fig_frame = ttk.Frame(self)
        fig_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        self._fig = Figure(figsize=(12, 5), dpi=88, tight_layout=True)
        self._ax_rows   = self._fig.add_subplot(1, 3, 1)
        self._ax_timing = self._fig.add_subplot(1, 3, 2)
        self._ax_logs   = self._fig.add_subplot(1, 3, 3)

        self._canvas = FigureCanvasTkAgg(self._fig, master=fig_frame)
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self._build_stats_panel()

    def _build_stats_panel(self) -> None:
        stats_lf = ttk.LabelFrame(self, text="Quick Stats")
        stats_lf.pack(fill=tk.X, padx=6, pady=(0, 6))

        self._stats_var = tk.StringVar(value="Press 'Refresh Now' to load statistics.")
        ttk.Label(
            stats_lf, textvariable=self._stats_var, font=("Courier", 9), justify=tk.LEFT
        ).pack(anchor=tk.W, padx=8, pady=6)

    # ------------------------------------------------------------------
    # Public callbacks
    # ------------------------------------------------------------------

    def on_db_changed(self) -> None:
        """Called when the active database changes."""
        if self._auto_active.get():
            self.refresh()

    def on_workspace_changed(self) -> None:
        pass  # Log health will be recalculated on next refresh

    # ------------------------------------------------------------------
    # Refresh logic
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        import datetime
        now = datetime.datetime.now().strftime("%H:%M:%S")

        # --- Data gathering ---
        row_counts = self.db.get_table_row_counts()
        query_timings = self.db.get_recent_query_timings(n=30)
        log_levels = _count_log_levels(self._scanner)

        # --- Quick stats ---
        db_size_str = "N/A"
        if self.db.db_path and self.db.db_path.exists():
            sz = self.db.db_path.stat().st_size
            db_size_str = f"{sz / 1024:.1f} KB" if sz < 1024 ** 2 else f"{sz / 1024 ** 2:.1f} MB"

        last_timing = ""
        if self.db.query_history:
            last = self.db.query_history[-1]
            last_timing = f"{last.elapsed_ms:.1f} ms ({'OK' if last.success else 'ERR'})"

        stats_text = (
            f"  Active DB     : {self.db.db_path.name if self.db.db_path else 'None'}\n"
            f"  DB Size       : {db_size_str}\n"
            f"  Total Tables  : {len(row_counts)}\n"
            f"  Last Query    : {last_timing}\n"
            f"  Log ERRORs    : {log_levels.get('ERROR', 0)}\n"
            f"  Log WARNINGs  : {log_levels.get('WARNING', 0)}\n"
            f"  Log INFOs     : {log_levels.get('INFO', 0)}\n"
        )
        self._stats_var.set(stats_text)

        if HAS_MATPLOTLIB:
            self._draw_charts(row_counts, query_timings, log_levels)

        self._last_refresh_var.set(f"Refreshed: {now}")
        self._status_set(f"Dashboard refreshed at {now}")

    def _draw_charts(self, row_counts, query_timings, log_levels) -> None:
        for ax in (self._ax_rows, self._ax_timing, self._ax_logs):
            ax.clear()

        # Chart 1: Table row counts
        ax = self._ax_rows
        if row_counts:
            names = list(row_counts.keys())
            values = [max(0, v) for v in row_counts.values()]
            colours = ["#1565C0" if v >= 0 else "#B71C1C" for v in list(row_counts.values())]
            bars = ax.bar(range(len(names)), values, color=colours, width=0.6)
            ax.set_xticks(range(len(names)))
            ax.set_xticklabels(names, rotation=30, ha="right", fontsize=7)
            ax.set_title("Table Row Counts", fontsize=9, fontweight="bold")
            ax.set_ylabel("Rows", fontsize=8)
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(
                lambda x, _: f"{int(x):,}"
            ))
            for bar, val in zip(bars, values):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.01,
                    f"{val:,}", ha="center", va="bottom", fontsize=6
                )
        else:
            ax.text(0.5, 0.5, "No tables", ha="center", va="center", transform=ax.transAxes)
            ax.set_title("Table Row Counts", fontsize=9, fontweight="bold")

        # Chart 2: Query timing history
        ax = self._ax_timing
        if query_timings:
            labels = [t[0] for t in query_timings]
            times = [t[1] for t in query_timings]
            success = [t[2] for t in query_timings]
            colours_t = ["#2E7D32" if s else "#B71C1C" for s in success]
            ax.bar(range(len(times)), times, color=colours_t, width=0.8)
            ax.set_title("Query Timings (last 30)", fontsize=9, fontweight="bold")
            ax.set_ylabel("ms", fontsize=8)
            ax.set_xlabel("Recent queries", fontsize=7)
            ax.set_xticks([])
        else:
            ax.text(0.5, 0.5, "No history yet", ha="center", va="center", transform=ax.transAxes)
            ax.set_title("Query Timings", fontsize=9, fontweight="bold")

        # Chart 3: Log health
        ax = self._ax_logs
        levels = ["INFO", "WARNING", "ERROR"]
        counts = [log_levels.get(l, 0) for l in levels]
        bar_colours = ["#388E3C", "#F57C00", "#C62828"]
        bars = ax.bar(levels, counts, color=bar_colours, width=0.5)
        ax.set_title("Log Level Distribution", fontsize=9, fontweight="bold")
        ax.set_ylabel("Line count", fontsize=8)
        for bar, val in zip(bars, counts):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(counts + [1]) * 0.02,
                f"{val:,}", ha="center", va="bottom", fontsize=8
            )

        self._canvas.draw()

    # ------------------------------------------------------------------
    # Auto-refresh
    # ------------------------------------------------------------------

    def _toggle_auto(self) -> None:
        if self._auto_active.get():
            self._schedule_next()
        else:
            self._cancel_auto()

    def _schedule_next(self) -> None:
        interval = max(2, self._interval_var.get()) * 1000
        self._auto_job = self.after(interval, self._auto_tick)

    def _auto_tick(self) -> None:
        self.refresh()
        if self._auto_active.get():
            self._schedule_next()

    def _cancel_auto(self) -> None:
        if self._auto_job:
            self.after_cancel(self._auto_job)
            self._auto_job = None
