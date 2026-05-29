"""
sql_editor_tab.py
-----------------
SQL Editor Tab with:
  - DBeaver-style cursor-aware statement execution (Ctrl+Enter)
  - Selected-text execution (overrides cursor detection)
  - SQL keyword / string / comment syntax highlighting
  - Intelligent autocomplete (keywords, table names, column names)
  - Custom Ctrl+Delete / Ctrl+Backspace (word-aware deletion)
  - Per-query execution timing displayed in status bar
  - Results piped directly to the DBBrowserTab data grid
"""
import re
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, List, Optional

from tools.db_manager import DBManager
from tools.autocomplete import AutocompletePopup
from tools.syntax_highlighter import SyntaxHighlighter, SQL_KEYWORDS


class SQLEditorTab(ttk.Frame):
    """
    Full-featured SQL editor panel.

    Dependencies injected via constructor:
      - db_manager  : DBManager  — executes queries and provides autocomplete data
      - on_result   : callable   — called with (rows, cols, elapsed_ms) to display results
      - status_set  : callable   — called with a string to update the app status bar
    """

    def __init__(
        self,
        parent,
        db_manager: DBManager,
        on_result: Callable,
        status_set: Callable[[str], None],
    ):
        super().__init__(parent)
        self.db = db_manager
        self._on_result = on_result
        self._status_set = status_set
        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=4, pady=(4, 0))

        ttk.Button(toolbar, text="Execute (Ctrl+Enter)", command=self._execute).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text="Clear", command=self._clear).pack(side=tk.LEFT, padx=2)

        self._timing_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self._timing_var, font=("Arial", 9)).pack(
            side=tk.RIGHT, padx=8
        )

        # Editor area
        editor_frame = ttk.Frame(self)
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Line numbers canvas
        self._line_canvas = tk.Canvas(editor_frame, width=38, bg="#F5F5F5")
        self._line_canvas.pack(side=tk.LEFT, fill=tk.Y)

        vsb = ttk.Scrollbar(editor_frame)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = ttk.Scrollbar(editor_frame, orient=tk.HORIZONTAL)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        self._editor = tk.Text(
            editor_frame,
            font=("Courier", 10),
            wrap=tk.NONE,
            undo=True,
            yscrollcommand=self._on_yscroll,
            xscrollcommand=hsb.set,
            insertbackground="#333333",
            tabs=("4c",),
        )
        self._editor.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=self._editor.yview)
        hsb.config(command=self._editor.xview)

        # Syntax highlighting
        self._highlighter = SyntaxHighlighter(self._editor)

        # Autocomplete
        self._autocomplete = AutocompletePopup(self._editor, self._get_suggestions)

        # Key bindings
        self._editor.bind("<Control-Return>", lambda e: (self._execute(), "break")[1])
        self._editor.bind("<KeyRelease>", self._on_key_release)
        self._editor.bind("<Control-Delete>",    self._ctrl_delete)
        self._editor.bind("<Control-BackSpace>", self._ctrl_backspace)
        self._editor.bind("<KeyRelease>", self._on_key_release)

        # Initial line numbers
        self._update_line_numbers()

    # ------------------------------------------------------------------
    # Public callbacks
    # ------------------------------------------------------------------

    def on_db_changed(self) -> None:
        """Called when the active database changes — autocomplete cache is stale."""
        pass  # DBManager already refreshed its cache

    # ------------------------------------------------------------------
    # Autocomplete suggestions
    # ------------------------------------------------------------------

    def _get_suggestions(self, word: str) -> List[str]:
        word_low = word.lower()
        seen: set = set()
        results: List[str] = []

        for kw in SQL_KEYWORDS:
            if kw.lower().startswith(word_low) and kw not in seen:
                seen.add(kw)
                results.append(kw)

        for t in self.db.all_tables:
            if t.lower().startswith(word_low) and t not in seen:
                seen.add(t)
                results.append(t)

        for c in self.db.all_columns:
            if c.lower().startswith(word_low) and c not in seen:
                seen.add(c)
                results.append(c)

        return results[:20]

    # ------------------------------------------------------------------
    # Key events
    # ------------------------------------------------------------------

    def _on_key_release(self, event) -> None:
        skip = {"Up", "Down", "Left", "Right", "Escape", "Return", "Tab",
                "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"}
        if event.keysym in skip:
            return

        self._highlighter.apply()
        self._update_line_numbers()

        # Extract partial word for autocomplete
        pos = self._editor.index(tk.INSERT)
        line, col = map(int, pos.split("."))
        line_text = self._editor.get(f"{line}.0", f"{line}.end")
        start = col
        while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] == "_"):
            start -= 1
        word = line_text[start:col]
        self._autocomplete.trigger(word)

    def _ctrl_delete(self, event) -> str:
        """Delete forward to next word boundary (space / underscore / punct)."""
        widget = event.widget
        pos = widget.index(tk.INSERT)
        line, col = map(int, pos.split("."))
        line_end = widget.index(f"{line}.end")

        if pos == line_end:
            widget.delete(pos, f"{line + 1}.0")
            self._highlighter.apply()
            return "break"

        text = widget.get(pos, line_end)
        if not text:
            return "break"

        n = 0
        c = text[0]
        if c.isspace():
            while n < len(text) and text[n].isspace():
                n += 1
        elif c == "_" or not c.isalnum():
            n = 1
        else:
            while n < len(text) and text[n].isalnum() and text[n] != "_":
                n += 1

        widget.delete(pos, f"{line}.{col + n}")
        self._highlighter.apply()
        return "break"

    def _ctrl_backspace(self, event) -> str:
        """Delete backward to previous word boundary."""
        widget = event.widget
        pos = widget.index(tk.INSERT)
        line, col = map(int, pos.split("."))

        if col == 0:
            if line > 1:
                widget.delete(f"{line - 1}.end", pos)
            self._highlighter.apply()
            return "break"

        text = widget.get(f"{line}.0", pos)
        rev = text[::-1]
        n = 0
        c = rev[0]
        if c.isspace():
            while n < len(rev) and rev[n].isspace():
                n += 1
        elif c == "_" or not c.isalnum():
            n = 1
        else:
            while n < len(rev) and rev[n].isalnum() and rev[n] != "_":
                n += 1

        widget.delete(f"{line}.{col - n}", pos)
        self._highlighter.apply()
        return "break"

    # ------------------------------------------------------------------
    # Execution logic (DBeaver-style cursor-aware)
    # ------------------------------------------------------------------

    def _get_statement_at_cursor(self) -> str:
        """
        Returns the SQL statement to execute using the following priority:
        1. Currently selected text (if any selection exists).
        2. The statement block under the cursor, delimited by semicolons.
        3. Entire editor content as fallback.
        """
        # Priority 1: selection
        try:
            selected = self._editor.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
            if selected:
                return selected
        except tk.TclError:
            pass

        # Priority 2: cursor-aware block split by ';'
        content = self._editor.get("1.0", tk.END)
        cursor_idx = self._editor.index(tk.INSERT)
        cursor_line, cursor_col = map(int, cursor_idx.split("."))
        lines = content.split("\n")
        cursor_offset = sum(len(l) + 1 for l in lines[: cursor_line - 1]) + cursor_col

        blocks: list = []
        current: list = []
        start_off = 0
        in_string = False
        str_char = ""

        for i, ch in enumerate(content):
            current.append(ch)
            if ch in ("'", '"') and (i == 0 or content[i - 1] != "\\"):
                if not in_string:
                    in_string, str_char = True, ch
                elif ch == str_char:
                    in_string = False
            if ch == ";" and not in_string:
                blocks.append(("".join(current), start_off, i + 1))
                current = []
                start_off = i + 1

        if current:
            blocks.append(("".join(current), start_off, len(content)))

        for block_text, s, e in blocks:
            if s <= cursor_offset <= e:
                stripped = block_text.strip()
                if stripped:
                    return stripped

        return content.strip()

    def _execute(self) -> None:
        query = self._get_statement_at_cursor()
        if not query:
            messagebox.showwarning("Warning", "No SQL query to execute.")
            return

        ok, rows, cols, err, rowcount, elapsed_ms = self.db.execute(query, commit=True)

        self._timing_var.set(f"Last: {elapsed_ms:.1f} ms")

        if not ok:
            messagebox.showerror("Query Error", f"{err}")
            self._status_set(f"ERROR — {elapsed_ms:.1f} ms")
            return

        if cols:
            # SELECT-style: pipe to browser
            self._on_result(rows, cols, elapsed_ms)
            self._status_set(f"OK — {rowcount} row(s) returned  |  {elapsed_ms:.1f} ms")
        else:
            messagebox.showinfo("Success", f"{rowcount} row(s) affected.  ({elapsed_ms:.1f} ms)")
            self._status_set(f"OK — {rowcount} row(s) affected  |  {elapsed_ms:.1f} ms")

    def _clear(self) -> None:
        self._editor.delete("1.0", tk.END)
        self._update_line_numbers()

    # ------------------------------------------------------------------
    # Line numbers
    # ------------------------------------------------------------------

    def _on_yscroll(self, *args) -> None:
        self._editor.yview(*args)
        self._update_line_numbers()

    def _update_line_numbers(self) -> None:
        self._line_canvas.delete("all")
        i = self._editor.index("@0,0")
        while True:
            dline = self._editor.dlineinfo(i)
            if dline is None:
                break
            y = dline[1]
            linenum = int(str(i).split(".")[0])
            self._line_canvas.create_text(
                34, y + 2,
                anchor=tk.NE,
                text=str(linenum),
                font=("Courier", 9),
                fill="#9E9E9E",
            )
            i = self._editor.index(f"{i}+1line")
