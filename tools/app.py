"""
app.py
------
Main application orchestrator for AMEVA Global DB Inspector v2.

Responsibilities
----------------
- Build the root Tkinter window (menu bar, top toolbar, tab notebook, status bar)
- Own the single DBManager and WorkspaceScanner instances
- Coordinate workspace/DB change events and broadcast them to all registered tabs
- Handle SQLite optimization dialog
- Provide the global status_set() interface consumed by all child tabs
"""
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import List

from tools.workspace_scanner import WorkspaceScanner
from tools.db_manager import DBManager
from tools.db_browser_tab import DBBrowserTab
from tools.sql_editor_tab import SQLEditorTab
from tools.log_explorer_tab import LogExplorerTab
from tools.csv_explorer_tab import CSVExplorerTab
from tools.dashboard_tab import DashboardTab


def _resolve_default_workspace(run_py_path: Path) -> Path:
    """
    Infer the default workspace from run.py location.
    Expected layout: <workspace>/<project>/run.py
    """
    project_root = run_py_path.resolve().parent
    workspace = project_root.parent
    return workspace if workspace.exists() else project_root


class AMEVAInspectorApp:
    """
    Top-level application class.
    Instantiate and call .run() to start the event loop.
    """

    APP_TITLE = "AMEVA Global DB Inspector  v2"

    def __init__(self, run_py_path: Path):
        self._workspace_root = _resolve_default_workspace(run_py_path)
        self._project_root = run_py_path.resolve().parent
        self._log_dir = self._project_root / "logs"

        # Core services
        self._scanner = WorkspaceScanner(self._workspace_root)
        self._db_manager = DBManager(self._log_dir)

        # Tkinter root
        self._root = tk.Tk()
        self._root.title(self.APP_TITLE)
        self._root.geometry("1280x820")
        self._root.minsize(900, 600)

        # Registered tabs (list of objects with on_db_changed() / on_workspace_changed())
        self._tabs: list = []

        self._build_ui()
        self._initial_scan()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._build_menu()
        self._build_toolbar()
        self._build_notebook()
        self._build_statusbar()

    def _build_menu(self) -> None:
        menubar = tk.Menu(self._root)

        # File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Workspace Folder...", command=self._browse_workspace)
        file_menu.add_command(label="Open DB File...",          command=self._open_db_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        # Tools
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Optimize SQLite (WAL + PRAGMA)", command=self._optimize_db)
        tools_menu.add_command(label="Rescan Workspace",                command=self._rescan)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        # Help
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label="About",
            command=lambda: messagebox.showinfo(
                "About",
                "AMEVA Global DB Inspector v2\n"
                "CPU-optimized edge AI database management tool.\n\n"
                "Part of the AMEVA project ecosystem.",
            ),
        )
        menubar.add_cascade(label="Help", menu=help_menu)

        self._root.config(menu=menubar)

    def _build_toolbar(self) -> None:
        tb = ttk.Frame(self._root)
        tb.pack(fill=tk.X, padx=6, pady=4)

        # Workspace
        ttk.Label(tb, text="Workspace:").pack(side=tk.LEFT)
        self._ws_var = tk.StringVar(value=str(self._workspace_root))
        ttk.Entry(tb, textvariable=self._ws_var, width=38, state="readonly").pack(
            side=tk.LEFT, padx=(4, 2)
        )
        ttk.Button(tb, text="Browse...", command=self._browse_workspace).pack(side=tk.LEFT)

        ttk.Separator(tb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # DB selector
        ttk.Label(tb, text="Active DB:").pack(side=tk.LEFT)
        self._db_combobox = ttk.Combobox(tb, width=44, state="readonly")
        self._db_combobox.pack(side=tk.LEFT, padx=(4, 2))
        self._db_combobox.bind("<<ComboboxSelected>>", self._on_db_selected)

        ttk.Button(tb, text="Open File...", command=self._open_db_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="Rescan",       command=self._rescan).pack(side=tk.LEFT, padx=2)

    def _build_notebook(self) -> None:
        self._notebook = ttk.Notebook(self._root)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))

        # 1. DB Browser
        self._db_browser = DBBrowserTab(self._notebook, self._db_manager)
        self._notebook.add(self._db_browser, text="DB Browser")
        self._tabs.append(self._db_browser)

        # 2. SQL Editor
        self._sql_editor = SQLEditorTab(
            self._notebook,
            self._db_manager,
            on_result=self._pipe_query_result,
            status_set=self._set_status,
        )
        self._notebook.add(self._sql_editor, text="SQL Editor")
        self._tabs.append(self._sql_editor)

        # 3. Log Explorer
        self._log_explorer = LogExplorerTab(
            self._notebook, self._scanner, status_set=self._set_status
        )
        self._notebook.add(self._log_explorer, text="Log Explorer")
        self._tabs.append(self._log_explorer)

        # 4. CSV Explorer
        self._csv_explorer = CSVExplorerTab(
            self._notebook, self._scanner, status_set=self._set_status
        )
        self._notebook.add(self._csv_explorer, text="CSV Explorer")
        self._tabs.append(self._csv_explorer)

        # 5. Dashboard
        self._dashboard = DashboardTab(
            self._notebook, self._db_manager, self._scanner,
            status_set=self._set_status,
        )
        self._notebook.add(self._dashboard, text="Dashboard")
        self._tabs.append(self._dashboard)

    def _build_statusbar(self) -> None:
        self._status_var = tk.StringVar(value="Ready.")
        bar = ttk.Label(
            self._root, textvariable=self._status_var,
            relief=tk.SUNKEN, anchor=tk.W, font=("Arial", 9),
        )
        bar.pack(fill=tk.X, side=tk.BOTTOM, padx=0, pady=0)

    # ------------------------------------------------------------------
    # Status helper
    # ------------------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        self._status_var.set(f"  {msg}")

    # ------------------------------------------------------------------
    # Workspace / DB management
    # ------------------------------------------------------------------

    def _initial_scan(self) -> None:
        self._rescan(select_first=True)

    def _rescan(self, select_first: bool = False) -> None:
        """Rebuild combobox from workspace DB scan; optionally auto-select first DB."""
        dbs = self._scanner.scan_databases()
        self._db_map: dict = dbs  # display_name -> Path

        names = list(dbs.keys())
        self._db_combobox["values"] = names

        if names:
            if select_first or not self._db_combobox.get() in names:
                self._db_combobox.set(names[0])
                self._switch_db(dbs[names[0]])
        else:
            self._db_combobox.set("")
            self._set_status("No .db files found in workspace.")

        # Refresh file-based tabs
        self._log_explorer.on_workspace_changed()
        self._csv_explorer.on_workspace_changed()

        self._set_status(
            f"Workspace: {self._workspace_root}  |  "
            f"{len(dbs)} DB(s)  |  "
            f"Scanned"
        )

    def _browse_workspace(self) -> None:
        folder = filedialog.askdirectory(
            initialdir=self._workspace_root, title="Select Workspace Folder"
        )
        if not folder:
            return
        self._workspace_root = Path(folder)
        self._scanner.workspace_path = self._workspace_root
        self._ws_var.set(str(self._workspace_root))
        self._rescan(select_first=True)

    def _open_db_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Open SQLite Database",
            filetypes=[
                ("SQLite DB", "*.db"),
                ("SQLite DB", "*.sqlite"),
                ("SQLite DB", "*.sqlite3"),
                ("All Files", "*.*"),
            ],
        )
        if not path:
            return
        p = Path(path)
        key = f"[External] {p.name}"
        self._db_map[key] = p

        vals = list(self._db_combobox["values"])
        if key not in vals:
            vals.append(key)
            self._db_combobox["values"] = vals

        self._db_combobox.set(key)
        self._switch_db(p)

    def _on_db_selected(self, _event=None) -> None:
        name = self._db_combobox.get()
        if name and name in self._db_map:
            self._switch_db(self._db_map[name])

    def _switch_db(self, db_path: Path) -> None:
        self._db_manager.set_database(db_path)
        for tab in self._tabs:
            if hasattr(tab, "on_db_changed"):
                tab.on_db_changed()
        self._set_status(f"Active DB: {db_path}")

    # ------------------------------------------------------------------
    # SQL result pipe: SQL Editor -> DB Browser data grid
    # ------------------------------------------------------------------

    def _pipe_query_result(self, rows, cols, elapsed_ms: float) -> None:
        self._db_browser.populate_from_query(rows, cols, elapsed_ms)
        # Switch to DB Browser tab so results are visible
        self._notebook.select(self._db_browser)

    # ------------------------------------------------------------------
    # SQLite Optimization
    # ------------------------------------------------------------------

    def _optimize_db(self) -> None:
        if not self._db_manager.db_path:
            messagebox.showwarning("Warning", "No active database selected.")
            return
        results = self._db_manager.apply_optimizations()
        lines = []
        for pragma, ok, err in results:
            status = "OK" if ok else f"FAIL: {err}"
            lines.append(f"  {pragma:<45} {status}")
        messagebox.showinfo(
            "SQLite Optimization Result",
            "\n".join(lines)
        )
        self._set_status("SQLite optimizations applied.")

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._root.mainloop()
