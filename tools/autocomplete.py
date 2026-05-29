"""
autocomplete.py
---------------
Intelligent SQL autocomplete popup for the Tkinter Text widget.
Supports keyboard navigation (Up/Down/Tab/Enter/Escape) and
double-click insertion.
"""
import tkinter as tk
from typing import Callable, List, Optional


class AutocompletePopup:
    """
    A floating Listbox popup that appears near the cursor in a Text widget
    and allows the user to select an autocomplete suggestion.

    The parent Text widget is responsible for triggering `.trigger(word)`
    after each keystroke with the current partial word.
    """

    def __init__(self, text_widget: tk.Text, get_suggestions: Callable[[str], List[str]]):
        self.text = text_widget
        self.get_suggestions = get_suggestions
        self._popup: Optional[tk.Toplevel] = None
        self._listbox: Optional[tk.Listbox] = None
        self._word_start: Optional[str] = None

        # Bind navigation keys on the text widget
        self.text.bind("<FocusOut>", lambda e: self.text.after(200, self._check_focus))
        self.text.bind("<KeyPress-Tab>", self._on_tab, add="+")
        self.text.bind("<KeyPress-Return>", self._on_return, add="+")
        self.text.bind("<KeyPress-Down>", self._on_down, add="+")
        self.text.bind("<KeyPress-Up>", self._on_up, add="+")
        self.text.bind("<KeyPress-Escape>", lambda e: self.hide(), add="+")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def trigger(self, word: str) -> None:
        """
        Called after each keystroke with the current partial word.
        Queries for suggestions and shows/hides the popup accordingly.
        """
        if len(word) < 1:
            self.hide()
            return

        suggestions = self.get_suggestions(word)
        if not suggestions:
            self.hide()
            return

        cursor_pos = self.text.index(tk.INSERT)
        line, col = map(int, cursor_pos.split("."))
        self._word_start = f"{line}.{col - len(word)}"
        self._show(suggestions)

    def hide(self) -> None:
        if self._popup and self._popup.winfo_exists():
            self._popup.withdraw()

    def is_visible(self) -> bool:
        return bool(
            self._popup
            and self._popup.winfo_exists()
            and self._popup.winfo_viewable()
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _show(self, suggestions: List[str]) -> None:
        if not self._popup:
            self._popup = tk.Toplevel(self.text.winfo_toplevel())
            self._popup.overrideredirect(True)
            self._popup.attributes("-topmost", True)
            self._listbox = tk.Listbox(
                self._popup,
                font=("Courier", 10),
                selectbackground="#0078d7",
                selectforeground="white",
                activestyle="none",
                relief=tk.FLAT,
                borderwidth=1,
            )
            self._listbox.pack(fill=tk.BOTH, expand=True)
            self._listbox.bind("<Double-Button-1>", lambda e: self._insert_selection())

        self._listbox.delete(0, tk.END)
        for s in suggestions:
            self._listbox.insert(tk.END, s)
        self._listbox.select_set(0)

        bbox = self.text.bbox(tk.INSERT)
        if bbox:
            x, y, _, h = bbox
            rx = self.text.winfo_rootx() + x
            ry = self.text.winfo_rooty() + y + h + 2
            height = min(len(suggestions) * 20 + 6, 160)
            self._popup.geometry(f"240x{height}+{rx}+{ry}")
            self._popup.deiconify()
            self._popup.lift()

    def _check_focus(self) -> None:
        if not self._popup or not self._popup.winfo_exists():
            return
        focused = self.text.focus_get()
        if focused not in (self._popup, self._listbox, self.text):
            self.hide()

    def _on_tab(self, event) -> Optional[str]:
        if self.is_visible():
            self._insert_selection()
            return "break"
        return None

    def _on_return(self, event) -> Optional[str]:
        if self.is_visible():
            self._insert_selection()
            return "break"
        return None

    def _on_down(self, event) -> Optional[str]:
        if self.is_visible():
            sel = self._listbox.curselection()
            if sel:
                idx = sel[0]
                if idx < self._listbox.size() - 1:
                    self._listbox.select_clear(idx)
                    self._listbox.select_set(idx + 1)
                    self._listbox.see(idx + 1)
            else:
                self._listbox.select_set(0)
            return "break"
        return None

    def _on_up(self, event) -> Optional[str]:
        if self.is_visible():
            sel = self._listbox.curselection()
            if sel:
                idx = sel[0]
                if idx > 0:
                    self._listbox.select_clear(idx)
                    self._listbox.select_set(idx - 1)
                    self._listbox.see(idx - 1)
            else:
                self._listbox.select_set(0)
            return "break"
        return None

    def _insert_selection(self) -> None:
        sel = self._listbox.curselection()
        if sel and self._word_start:
            value = self._listbox.get(sel[0])
            cur = self.text.index(tk.INSERT)
            self.text.delete(self._word_start, cur)
            self.text.insert(self._word_start, value)
            self.text.event_generate("<<ContentChanged>>")
        self.hide()
