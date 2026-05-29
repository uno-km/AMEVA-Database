"""
db_browser_tab.py
-----------------
Database Browser Tab: shows table list, schema, data grid, and CRUD dialogs.
All queries are routed through DBManager for logging and timing.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Optional

from tools.db_manager import DBManager


def _make_scrolled_tree(parent) -> tuple:
    """Helper: create a Treeview with both scrollbars. Returns (frame, tree)."""
    frame = ttk.Frame(parent)
    vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL)
    hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL)
    tree = ttk.Treeview(
        frame,
        yscrollcommand=vsb.set,
        xscrollcommand=hsb.set,
        show="headings",
    )
    vsb.config(command=tree.yview)
    hsb.config(command=tree.xview)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    hsb.pack(side=tk.BOTTOM, fill=tk.X)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    return frame, tree


class CRUDDialog(tk.Toplevel):
    """
    Generic modal dialog for INSERT / UPDATE operations.
    Builds a scrollable form from the list of column names.
    PK fields are disabled during UPDATE to prevent accidental mutation.
    """

    def __init__(self, parent, title: str, columns: List[str],
                 primary_keys: List[str], prefill: Optional[dict] = None,
                 on_submit=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._columns = columns
        self._primary_keys = primary_keys
        self._on_submit = on_submit
        self._entries: dict = {}

        self._build(prefill or {})
        self.geometry("420x520")
        self.wait_window()

    def _build(self, prefill: dict) -> None:
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        canvas = tk.Canvas(container, borderwidth=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for i, col in enumerate(self._columns):
            is_pk = col in self._primary_keys
            label_text = f"{col}  [PK]" if is_pk else col
            ttk.Label(scroll_frame, text=label_text, font=("Arial", 9)).grid(
                row=i, column=0, sticky=tk.W, padx=6, pady=4
            )
            entry = ttk.Entry(scroll_frame, width=32)
            val = prefill.get(col, "")
            if val is not None:
                entry.insert(0, str(val))
            if is_pk and prefill:
                entry.config(state=tk.DISABLED)
            entry.grid(row=i, column=1, sticky=tk.EW, padx=6, pady=4)
            self._entries[col] = entry

        btn_row = len(self._columns)
        ttk.Button(
            scroll_frame, text="Submit", command=self._submit
        ).grid(row=btn_row, column=0, columnspan=2, pady=10)

    def _submit(self) -> None:
        data = {}
        for col, entry in self._entries.items():
            raw = entry.get().strip()
            data[col] = raw if raw != "" else None
        if self._on_submit:
            self._on_submit(data)
        self.destroy()


class DBBrowserTab(ttk.Frame):
    """
    Main database browsing panel.

    Layout
    ------
    Left sidebar  : table listbox
    Right top     : scrolled Treeview data grid (LIMIT 1000)
    Right bottom  : Notebook with Schema tab and CRUD Controls tab
    """

    def __init__(self, parent, db_manager: DBManager):
        super().__init__(parent)
        self.db = db_manager
        self.current_table: Optional[str] = None
        self.columns: List[str] = []
        self.primary_keys: List[str] = []

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # --- Left sidebar ---
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        ttk.Label(left, text="Tables", font=("Arial", 11, "bold")).pack(
            anchor=tk.W, padx=4, pady=(4, 0)
        )
        lf = ttk.Frame(left)
        lf.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        sb = ttk.Scrollbar(lf)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._table_listbox = tk.Listbox(lf, font=("Arial", 10), yscrollcommand=sb.set)
        self._table_listbox.pack(fill=tk.BOTH, expand=True)
        sb.config(command=self._table_listbox.yview)
        self._table_listbox.bind("<<ListboxSelect>>", self._on_table_select)

        ttk.Button(left, text="Refresh Tables", command=self.refresh_tables).pack(
            fill=tk.X, padx=4, pady=(0, 4)
        )

        # --- Right pane ---
        right_paned = ttk.PanedWindow(paned, orient=tk.VERTICAL)
        paned.add(right_paned, weight=4)

        # Top: data grid
        top_frame = ttk.Frame(right_paned)
        right_paned.add(top_frame, weight=3)

        ttk.Label(top_frame, text="Data Browser", font=("Arial", 11, "bold")).pack(
            anchor=tk.W, padx=4, pady=(4, 0)
        )
        grid_frame, self._data_tree = _make_scrolled_tree(top_frame)
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Bottom: schema + CRUD
        bottom_nb = ttk.Notebook(right_paned)
        right_paned.add(bottom_nb, weight=2)

        self._build_schema_tab(bottom_nb)
        self._build_crud_tab(bottom_nb)

    def _build_schema_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Schema")

        self._schema_text = tk.Text(
            frame, font=("Courier", 9), state=tk.DISABLED, wrap=tk.NONE
        )
        vsb = ttk.Scrollbar(frame, command=self._schema_text.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self._schema_text.xview)
        self._schema_text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._schema_text.pack(fill=tk.BOTH, expand=True)

    def _build_crud_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="CRUD Controls")

        btn_cfg = dict(fill=tk.X, padx=8, pady=3)
        ttk.Button(frame, text="Refresh Data",    command=self.load_data).pack(**btn_cfg)
        ttk.Button(frame, text="Insert Record",   command=self._show_insert).pack(**btn_cfg)
        ttk.Button(frame, text="Update Selected", command=self._show_update).pack(**btn_cfg)
        ttk.Button(frame, text="Delete Selected", command=self._delete).pack(**btn_cfg)

        # Row count label
        self._row_count_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self._row_count_var, font=("Arial", 9)).pack(
            anchor=tk.W, padx=8, pady=(6, 0)
        )

    # ------------------------------------------------------------------
    # Public callbacks
    # ------------------------------------------------------------------

    def on_db_changed(self) -> None:
        """Called by App when the active database changes."""
        self.current_table = None
        self.columns = []
        self.primary_keys = []
        self._table_listbox.delete(0, tk.END)
        self._data_tree.delete(*self._data_tree.get_children())
        self._data_tree["columns"] = []
        self._set_schema("")
        self._row_count_var.set("")
        self.refresh_tables()

    def refresh_tables(self) -> None:
        self._table_listbox.delete(0, tk.END)
        ok, rows, _, err, _, _ = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        )
        if not ok:
            messagebox.showerror("Error", f"Failed to load tables:\n{err}")
            return
        for row in rows:
            self._table_listbox.insert(tk.END, row["name"])

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_table_select(self, _event) -> None:
        sel = self._table_listbox.curselection()
        if not sel:
            return
        self.current_table = self._table_listbox.get(sel[0])
        self._load_schema()
        self.load_data()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _load_schema(self) -> None:
        if not self.current_table:
            return
        ok, rows, _, err, _, _ = self.db.execute(
            f"PRAGMA table_info({self.current_table});"
        )
        if not ok:
            messagebox.showerror("Error", f"Schema load failed:\n{err}")
            return

        self.columns = []
        self.primary_keys = []

        lines = [f"{'CID':<4} {'Name':<20} {'Type':<12} {'NotNull':<8} {'Default':<12} PK"]
        lines.append("-" * 62)
        for col in rows:
            cid = col["cid"]
            name = col["name"]
            dtype = col["type"] or ""
            notnull = col["notnull"]
            dflt = col["dflt_value"] or ""
            pk = col["pk"]
            lines.append(f"{cid:<4} {name:<20} {dtype:<12} {notnull:<8} {dflt:<12} {pk}")
            self.columns.append(name)
            if pk > 0:
                self.primary_keys.append(name)

        self._set_schema("\n".join(lines))

        # Reset data grid columns
        self._data_tree.delete(*self._data_tree.get_children())
        self._data_tree["columns"] = self.columns
        for col in self.columns:
            self._data_tree.heading(col, text=col, anchor=tk.W)
            self._data_tree.column(col, width=110, anchor=tk.W, stretch=True)

    def _set_schema(self, text: str) -> None:
        self._schema_text.config(state=tk.NORMAL)
        self._schema_text.delete("1.0", tk.END)
        self._schema_text.insert("1.0", text)
        self._schema_text.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_data(self) -> None:
        if not self.current_table:
            return
        ok, rows, cols, err, count, elapsed = self.db.execute(
            f"SELECT * FROM {self.current_table} LIMIT 1000;"
        )
        if not ok:
            messagebox.showerror("Error", f"Data load failed:\n{err}")
            return

        # Refresh tree columns if needed
        if cols and list(self._data_tree["columns"]) != cols:
            self.columns = cols
            self._data_tree["columns"] = cols
            for col in cols:
                self._data_tree.heading(col, text=col, anchor=tk.W)
                self._data_tree.column(col, width=110, anchor=tk.W, stretch=True)

        self._data_tree.delete(*self._data_tree.get_children())
        for row in rows:
            values = ["" if row[c] is None else row[c] for c in self.columns]
            self._data_tree.insert("", tk.END, values=values)

        self._row_count_var.set(f"{count} row(s) loaded  |  {elapsed:.1f} ms")

    def populate_from_query(self, rows, cols: List[str], elapsed_ms: float) -> None:
        """Called by SQLEditorTab to display arbitrary query results."""
        self._data_tree.delete(*self._data_tree.get_children())
        self._data_tree["columns"] = cols
        for col in cols:
            self._data_tree.heading(col, text=col, anchor=tk.W)
            self._data_tree.column(col, width=110, anchor=tk.W, stretch=True)
        for row in rows:
            values = ["" if row[c] is None else row[c] for c in cols]
            self._data_tree.insert("", tk.END, values=values)
        self.columns = cols
        self._row_count_var.set(f"{len(rows)} row(s)  |  {elapsed_ms:.1f} ms")

    # ------------------------------------------------------------------
    # CRUD dialogs
    # ------------------------------------------------------------------

    def _show_insert(self) -> None:
        if not self.current_table:
            messagebox.showwarning("Warning", "Select a table first.")
            return

        def on_submit(data: dict):
            non_empty = {k: v for k, v in data.items() if v is not None}
            if not non_empty:
                messagebox.showerror("Error", "No values provided.")
                return
            cols = ", ".join(non_empty.keys())
            placeholders = ", ".join("?" * len(non_empty))
            query = f"INSERT INTO {self.current_table} ({cols}) VALUES ({placeholders})"
            ok, _, _, err, _, _ = self.db.execute(query, list(non_empty.values()), commit=True)
            if ok:
                self.load_data()
                messagebox.showinfo("Success", "Record inserted.")
            else:
                messagebox.showerror("DB Error", err)

        CRUDDialog(self, f"Insert into {self.current_table}",
                   self.columns, self.primary_keys, on_submit=on_submit)

    def _show_update(self) -> None:
        sel = self._data_tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select a record to update.")
            return
        if not self.primary_keys:
            messagebox.showerror("Error", "Cannot UPDATE: table has no Primary Key.")
            return

        values = self._data_tree.item(sel[0])["values"]
        prefill = dict(zip(self.columns, values))

        def on_submit(data: dict):
            set_parts = [f"{c} = ?" for c in self.columns if c not in self.primary_keys]
            set_vals = [data[c] for c in self.columns if c not in self.primary_keys]
            where_parts = [f"{pk} = ?" for pk in self.primary_keys]
            where_vals = [prefill[pk] for pk in self.primary_keys]
            query = (
                f"UPDATE {self.current_table} "
                f"SET {', '.join(set_parts)} "
                f"WHERE {' AND '.join(where_parts)}"
            )
            ok, _, _, err, rc, _ = self.db.execute(query, set_vals + where_vals, commit=True)
            if ok:
                self.load_data()
                messagebox.showinfo("Success", f"{rc} row(s) updated.")
            else:
                messagebox.showerror("DB Error", err)

        CRUDDialog(self, f"Update — {self.current_table}",
                   self.columns, self.primary_keys, prefill=prefill, on_submit=on_submit)

    def _delete(self) -> None:
        sel = self._data_tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select a record to delete.")
            return
        if not self.primary_keys:
            messagebox.showerror("Error", "Cannot DELETE: table has no Primary Key.")
            return
        if not messagebox.askyesno("Confirm", "Delete the selected record? This cannot be undone."):
            return

        values = self._data_tree.item(sel[0])["values"]
        prefill = dict(zip(self.columns, values))
        where_parts = [f"{pk} = ?" for pk in self.primary_keys]
        where_vals = [prefill[pk] for pk in self.primary_keys]
        query = f"DELETE FROM {self.current_table} WHERE {' AND '.join(where_parts)}"

        ok, _, _, err, rc, _ = self.db.execute(query, where_vals, commit=True)
        if ok:
            self.load_data()
            messagebox.showinfo("Success", f"{rc} row(s) deleted.")
        else:
            messagebox.showerror("DB Error", err)
