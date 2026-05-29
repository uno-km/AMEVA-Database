"""
syntax_highlighter.py
---------------------
Real-time SQL syntax highlighting for a Tkinter Text widget.
Highlights: SQL keywords (bold, dark brown), string literals (green),
single-line comments (grey italic), and numbers (blue).
"""
import re
import tkinter as tk
from tkinter.font import Font

SQL_KEYWORDS = [
    "SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE", "JOIN",
    "LEFT", "RIGHT", "INNER", "OUTER", "FULL", "CROSS",
    "AND", "OR", "NOT", "IN", "IS", "NULL", "LIKE", "BETWEEN", "EXISTS",
    "LIMIT", "OFFSET", "ORDER", "BY", "GROUP", "HAVING", "DISTINCT",
    "INTO", "VALUES", "SET", "AS", "ON",
    "CREATE", "TABLE", "DROP", "ALTER", "INDEX",
    "PRAGMA", "BEGIN", "COMMIT", "ROLLBACK", "TRANSACTION",
    "COUNT", "SUM", "AVG", "MAX", "MIN", "COALESCE", "IFNULL",
    "CASE", "WHEN", "THEN", "ELSE", "END",
    "UNION", "ALL", "INTERSECT", "EXCEPT",
    "ASC", "DESC", "WITH", "RECURSIVE",
]

# Compiled patterns
_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(SQL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
_STRING_RE = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_COMMENT_RE = re.compile(r"--[^\n]*")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


class SyntaxHighlighter:
    """
    Applies real-time syntax highlighting to a Tkinter Text widget.

    Call `.apply()` manually or bind it to the <<ContentChanged>> event.
    Uses Tag system (no external rendering) — zero additional dependencies.
    """

    TAG_KEYWORD = "hl_keyword"
    TAG_STRING = "hl_string"
    TAG_COMMENT = "hl_comment"
    TAG_NUMBER = "hl_number"

    def __init__(self, text_widget: tk.Text):
        self.text = text_widget
        self._configure_tags()
        self.text.bind("<<ContentChanged>>", lambda e: self.apply())

    def _configure_tags(self) -> None:
        base_font = ("Courier", 10)
        bold_font = ("Courier", 10, "bold")
        italic_font = ("Courier", 10, "italic")

        self.text.tag_configure(self.TAG_KEYWORD,  foreground="#5C2D16", font=bold_font)
        self.text.tag_configure(self.TAG_STRING,   foreground="#2E7D32", font=base_font)
        self.text.tag_configure(self.TAG_COMMENT,  foreground="#9E9E9E", font=italic_font)
        self.text.tag_configure(self.TAG_NUMBER,   foreground="#1565C0", font=base_font)

    def apply(self) -> None:
        """Remove all highlight tags and re-apply from scratch."""
        for tag in (self.TAG_KEYWORD, self.TAG_STRING, self.TAG_COMMENT, self.TAG_NUMBER):
            self.text.tag_remove(tag, "1.0", tk.END)

        content = self.text.get("1.0", tk.END)

        # Build a mask of positions already covered by strings/comments
        # so keywords inside strings are not highlighted.
        masked: list = [False] * len(content)

        # --- Strings (highest priority) ---
        for m in _STRING_RE.finditer(content):
            for i in range(m.start(), m.end()):
                masked[i] = True
            self._tag(self.TAG_STRING, m.start(), m.end())

        # --- Single-line comments ---
        for m in _COMMENT_RE.finditer(content):
            for i in range(m.start(), m.end()):
                masked[i] = True
            self._tag(self.TAG_COMMENT, m.start(), m.end())

        # --- Keywords (only outside masked regions) ---
        for m in _KEYWORD_RE.finditer(content):
            if not masked[m.start()]:
                self._tag(self.TAG_KEYWORD, m.start(), m.end())

        # --- Numbers (only outside masked regions) ---
        for m in _NUMBER_RE.finditer(content):
            if not masked[m.start()]:
                self._tag(self.TAG_NUMBER, m.start(), m.end())

    def _tag(self, tag: str, start: int, end: int) -> None:
        self.text.tag_add(tag, f"1.0 + {start}c", f"1.0 + {end}c")
