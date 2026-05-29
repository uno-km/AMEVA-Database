import os
import sys
import sqlite3
import logging
import logging.handlers
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

class AutocompletePopup:
    def __init__(self, text_widget, get_suggestions_cb):
        self.text = text_widget
        self.get_suggestions = get_suggestions_cb
        self.popup = None
        self.listbox = None
        self.suggestions = []
        self.current_word_start = None
        self.current_word_end = None

        self.text.bind("<FocusOut>", lambda e: self.text.after(200, self.check_focus))
        self.text.bind("<KeyPress-Tab>", self.on_tab, add="+")
        self.text.bind("<KeyPress-Return>", self.on_return, add="+")
        self.text.bind("<KeyPress-Down>", self.on_down, add="+")
        self.text.bind("<KeyPress-Up>", self.on_up, add="+")
        self.text.bind("<KeyPress-Escape>", lambda e: self.hide(), add="+")

    def show(self, suggestions, word_start, word_end):
        self.suggestions = suggestions
        self.current_word_start = word_start
        self.current_word_end = word_end
        
        if not self.popup:
            self.popup = tk.Toplevel(self.text.winfo_toplevel())
            self.popup.overrideredirect(True)
            self.listbox = tk.Listbox(self.popup, font=("Courier", 10), selectbackground="#0078d7", selectforeground="white")
            self.listbox.pack(fill=tk.BOTH, expand=True)
            self.listbox.bind("<Double-Button-1>", lambda e: self.insert_selection())

        self.listbox.delete(0, tk.END)
        for s in self.suggestions:
            self.listbox.insert(tk.END, s)
        self.listbox.select_set(0)

        # Position popup near cursor
        bbox = self.text.bbox(tk.INSERT)
        if bbox:
            x, y, w, h = bbox
            root_x = self.text.winfo_rootx() + x
            root_y = self.text.winfo_rooty() + y + h + 2
            self.popup.geometry(f"200x150+{root_x}+{root_y}")
            self.popup.deiconify()
            self.popup.lift()

    def hide(self):
        if self.popup and self.popup.winfo_exists():
            self.popup.withdraw()

    def is_visible(self):
        return self.popup and self.popup.winfo_exists() and self.popup.winfo_viewable()

    def check_focus(self):
        if not self.popup or not self.popup.winfo_exists():
            return
        focused = self.text.focus_get()
        if focused not in (self.popup, self.listbox, self.text):
            self.hide()

    def on_key_release(self, word):
        # Receive the current word directly from parent app's event handler
        if len(word) >= 1:
            suggestions = self.get_suggestions(word)
            if suggestions:
                cursor_pos = self.text.index(tk.INSERT)
                line, col = map(int, cursor_pos.split('.'))
                start_col = col - len(word)
                self.show(suggestions, f"{line}.{start_col}", f"{line}.{col}")
            else:
                self.hide()
        else:
            self.hide()

    def on_tab(self, event):
        if self.is_visible():
            self.insert_selection()
            return "break"

    def on_return(self, event):
        if self.is_visible():
            self.insert_selection()
            return "break"

    def on_down(self, event):
        if self.is_visible():
            curr = self.listbox.curselection()
            if curr:
                idx = curr[0]
                if idx < self.listbox.size() - 1:
                    self.listbox.select_clear(idx)
                    self.listbox.select_set(idx + 1)
                    self.listbox.see(idx + 1)
            else:
                self.listbox.select_set(0)
            return "break"

    def on_up(self, event):
        if self.is_visible():
            curr = self.listbox.curselection()
            if curr:
                idx = curr[0]
                if idx > 0:
                    self.listbox.select_clear(idx)
                    self.listbox.select_set(idx - 1)
                    self.listbox.see(idx - 1)
            else:
                self.listbox.select_set(0)
            return "break"

    def insert_selection(self):
        curr = self.listbox.curselection()
        if curr and self.current_word_start:
            selected_val = self.listbox.get(curr[0])
            cursor_pos = self.text.index(tk.INSERT)
            self.text.delete(self.current_word_start, cursor_pos)
            self.text.insert(self.current_word_start, selected_val)
            # Retrigger syntax highlighting on insert
            self.text.event_generate("<<Highlight>>")
        self.hide()


class DBInspectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Global DB Inspector")
        self.root.geometry("1100x750")

        self.db_path = None
        self.current_table = None
        self.primary_keys = []
        self.columns = []
        self.discovered_dbs = {} # display_name -> Path object
        
        self.sql_keywords = [
            "SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE", "JOIN", 
            "AND", "OR", "LIMIT", "INTO", "VALUES", "SET", "CREATE", "TABLE", 
            "DROP", "AS", "ON", "ORDER", "BY", "GROUP", "HAVING", "LEFT", 
            "RIGHT", "INNER", "OUTER", "IN", "IS", "NULL", "NOT", "LIKE"
        ]
        self.all_tables = []
        self.all_columns = set()

        # Determine default workspace & repo paths
        current_dir = Path(__file__).resolve().parent
        if current_dir.name == "tools":
            self.repo_root = current_dir.parent
            self.workspace_path = current_dir.parent.parent 
        else:
            self.repo_root = current_dir
            self.workspace_path = current_dir.parent

        self.setup_logging()
        self.setup_ui()
        self.scan_workspace(self.workspace_path)

    def setup_logging(self):
        log_dir = self.repo_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        self.log_file = log_dir / "db_inspector.log"
        
        self.logger = logging.getLogger("DBInspector")
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            file_handler = logging.handlers.RotatingFileHandler(
                self.log_file, maxBytes=1024*1024, backupCount=3, encoding="utf-8"
            )
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            
        self.logger.info("DB Inspector tool initialized.")

    def scan_workspace(self, workspace):
        self.workspace_path_var.set(str(workspace))
        self.discovered_dbs = {}
        
        try:
            for p in workspace.rglob("*.db"):
                if "venv" in p.parts or "node_modules" in p.parts or "__pycache__" in p.parts or ".git" in p.parts:
                    continue
                try:
                    rel_path = p.relative_to(workspace)
                    display_name = str(rel_path)
                except ValueError:
                    display_name = str(p)
                self.discovered_dbs[display_name] = p
                
            for p in workspace.rglob("*.sqlite"):
                if "venv" in p.parts or "node_modules" in p.parts or "__pycache__" in p.parts or ".git" in p.parts:
                    continue
                try:
                    rel_path = p.relative_to(workspace)
                    display_name = str(rel_path)
                except ValueError:
                    display_name = str(p)
                self.discovered_dbs[display_name] = p
                
        except Exception as e:
            messagebox.showwarning("Scan Warning", f"Could not scan directory fully: {e}")
            
        db_names = list(self.discovered_dbs.keys())
        db_names.sort()
        self.db_combobox['values'] = db_names
        
        if db_names:
            self.db_combobox.set(db_names[0])
            self.on_db_select()
        else:
            self.db_combobox.set("")
            self.table_listbox.delete(0, tk.END)
            self.data_tree.delete(*self.data_tree.get_children())
            self.db_path = None

    def browse_workspace(self):
        folder = filedialog.askdirectory(initialdir=self.workspace_path, title="Select Workspace Folder")
        if folder:
            self.scan_workspace(Path(folder))

    def open_db_file(self):
        file_path = filedialog.askopenfilename(
            title="Select SQLite Database",
            filetypes=[("SQLite DB", "*.db"), ("SQLite DB", "*.sqlite"), ("All Files", "*.*")]
        )
        if file_path:
            p = Path(file_path)
            display_name = f"[External] {p.name}"
            self.discovered_dbs[display_name] = p
            
            vals = list(self.db_combobox['values'])
            if display_name not in vals:
                vals.append(display_name)
                self.db_combobox['values'] = vals
            
            self.db_combobox.set(display_name)
            self.on_db_select()

    def on_db_select(self, event=None):
        selected = self.db_combobox.get()
        if selected in self.discovered_dbs:
            self.db_path = self.discovered_dbs[selected]
            self.current_table = None
            self.schema_text.config(state=tk.NORMAL)
            self.schema_text.delete(1.0, tk.END)
            self.schema_text.config(state=tk.DISABLED)
            self.data_tree.delete(*self.data_tree.get_children())
            self.data_tree["columns"] = []
            self.logger.info(f"Switched database to: {self.db_path}")
            self.load_tables()

    def get_connection(self):
        if not self.db_path:
            return None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to connect to database:\n{e}")
            return None

    def execute_query(self, query, params=None, commit=False):
        if not self.db_path:
            return False, None, None, "No database selected", 0
            
        conn = self.get_connection()
        if not conn:
            return False, None, None, "Failed to connect to database", 0
            
        cursor = conn.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
                
            rowcount = cursor.rowcount
            
            if cursor.description is not None:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                if commit:
                    conn.commit()
                self.logger.info(f"DB: {self.db_path.name} | SQL: {query} | Params: {params} | SUCCESS | Rows: {len(rows)}")
                return True, rows, columns, None, len(rows)
            else:
                if commit:
                    conn.commit()
                self.logger.info(f"DB: {self.db_path.name} | SQL: {query} | Params: {params} | SUCCESS | Affected: {rowcount}")
                return True, None, None, None, rowcount
                
        except sqlite3.Error as e:
            self.logger.error(f"DB: {self.db_path.name} | SQL: {query} | Params: {params} | ERROR: {e}")
            return False, None, None, str(e), 0
        finally:
            conn.close()

    def setup_ui(self):
        # Top Bar for Workspace/DB Selection
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(top_frame, text="Workspace:").pack(side=tk.LEFT, padx=(0, 5))
        self.workspace_path_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.workspace_path_var, width=40, state="readonly").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(top_frame, text="Browse Folder...", command=self.browse_workspace).pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Label(top_frame, text="Select DB:").pack(side=tk.LEFT, padx=(0, 5))
        self.db_combobox = ttk.Combobox(top_frame, width=45, state="readonly")
        self.db_combobox.pack(side=tk.LEFT, padx=(0, 5))
        self.db_combobox.bind("<<ComboboxSelected>>", self.on_db_select)
        
        ttk.Button(top_frame, text="Open File...", command=self.open_db_file).pack(side=tk.LEFT)

        # Main PanedWindow (Left/Right)
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left Panel (Table List)
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Tables", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=2)
        
        self.table_listbox = tk.Listbox(left_frame, font=("Arial", 11))
        self.table_listbox.pack(fill=tk.BOTH, expand=True)
        self.table_listbox.bind("<<ListboxSelect>>", self.on_table_select)

        # Right Panel (Top/Bottom)
        right_paned = ttk.PanedWindow(main_paned, orient=tk.VERTICAL)
        main_paned.add(right_paned, weight=4)

        # Top Right Panel (Data Grid)
        top_right_frame = ttk.Frame(right_paned)
        right_paned.add(top_right_frame, weight=3)

        ttk.Label(top_right_frame, text="Data Browser", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=2)
        
        tree_frame = ttk.Frame(top_right_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        tree_scroll_y = ttk.Scrollbar(tree_frame)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.data_tree = ttk.Treeview(tree_frame, yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set, show="headings")
        self.data_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tree_scroll_y.config(command=self.data_tree.yview)
        tree_scroll_x.config(command=self.data_tree.xview)

        # Bottom Right Panel (Schema, Controls, SQL)
        bottom_right_frame = ttk.Frame(right_paned)
        right_paned.add(bottom_right_frame, weight=2)

        self.bottom_notebook = ttk.Notebook(bottom_right_frame)
        self.bottom_notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        # Tab 1: Operations (Schema + CRUD)
        ops_frame = ttk.Frame(self.bottom_notebook)
        self.bottom_notebook.add(ops_frame, text="Operations & Schema")

        schema_frame = ttk.LabelFrame(ops_frame, text="Table Schema")
        schema_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.schema_text = tk.Text(schema_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Courier", 10))
        self.schema_text.pack(fill=tk.BOTH, expand=True)

        controls_frame = ttk.LabelFrame(ops_frame, text="CRUD Controls")
        controls_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        ttk.Button(controls_frame, text="Refresh Data", command=self.load_table_data).pack(fill=tk.X, pady=2, padx=5)
        ttk.Button(controls_frame, text="Insert Record", command=self.insert_record).pack(fill=tk.X, pady=2, padx=5)
        ttk.Button(controls_frame, text="Update Selected", command=self.update_record).pack(fill=tk.X, pady=2, padx=5)
        ttk.Button(controls_frame, text="Delete Selected", command=self.delete_record).pack(fill=tk.X, pady=2, padx=5)

        # Tab 2: Raw SQL
        sql_frame = ttk.Frame(self.bottom_notebook)
        self.bottom_notebook.add(sql_frame, text="Raw SQL Editor")

        self.sql_text = tk.Text(sql_frame, wrap=tk.WORD, height=5, font=("Courier", 10))
        self.sql_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Configure tags for Syntax Highlighting
        self.sql_text.tag_config("keyword", foreground="#5C2D16", font=("Courier", 10, "bold"))
        
        # Keyboard and event bindings
        self.sql_text.bind("<Control-Return>", self.on_sql_ctrl_enter)
        self.sql_text.bind("<KeyRelease>", self.on_sql_key_release)
        self.sql_text.bind("<<Highlight>>", lambda e: self.highlight_keywords())
        
        # Bindings for custom Ctrl+Delete and Ctrl+Backspace
        self.sql_text.bind("<Control-Delete>", self.on_ctrl_delete)
        self.sql_text.bind("<Control-BackSpace>", self.on_ctrl_backspace)
        
        # Setup Auto-Complete
        self.autocomplete = AutocompletePopup(self.sql_text, self.get_suggestions)

        ttk.Button(sql_frame, text="Execute SQL (Ctrl+Enter)", command=self.execute_raw_sql).pack(anchor=tk.E, padx=5, pady=5)

    def on_sql_key_release(self, event):
        if event.keysym in ("Up", "Down", "Left", "Right", "Escape", "Return", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
            
        self.highlight_keywords()
        
        # Extract word under cursor for autocomplete popup
        cursor_pos = self.sql_text.index(tk.INSERT)
        line, col = map(int, cursor_pos.split('.'))
        line_text = self.sql_text.get(f"{line}.0", f"{line}.end")
        
        start = col
        while start > 0 and (line_text[start-1].isalnum() or line_text[start-1] in '_'):
            start -= 1
            
        word = line_text[start:col]
        self.autocomplete.on_key_release(word)

    def highlight_keywords(self):
        self.sql_text.tag_remove("keyword", "1.0", tk.END)
        content = self.sql_text.get("1.0", tk.END)
        
        # Match keywords as whole words case-insensitively
        pattern = r'\b(' + '|'.join(self.sql_keywords) + r')\b'
        for match in re.finditer(pattern, content, re.IGNORECASE):
            start = match.start()
            end = match.end()
            self.sql_text.tag_add("keyword", f"1.0 + {start} chars", f"1.0 + {end} chars")

    def on_ctrl_delete(self, event):
        text_widget = event.widget
        insert_pos = text_widget.index(tk.INSERT)
        line, col = map(int, insert_pos.split('.'))
        line_end = text_widget.index(f"{line}.end")
        
        if insert_pos == line_end:
            # Delete newline character at the end of the line
            text_widget.delete(insert_pos, f"{line+1}.0")
            self.highlight_keywords()
            return "break"
            
        line_text = text_widget.get(insert_pos, line_end)
        if not line_text:
            return "break"
            
        delete_len = 0
        first_char = line_text[0]
        
        if first_char.isspace():
            while delete_len < len(line_text) and line_text[delete_len].isspace():
                delete_len += 1
        elif first_char == '_':
            delete_len = 1
        elif first_char.isalnum():
            while delete_len < len(line_text) and line_text[delete_len].isalnum():
                if line_text[delete_len] == '_':
                    break
                delete_len += 1
        else:
            delete_len = 1
            
        end_pos = f"{line}.{col + delete_len}"
        text_widget.delete(insert_pos, end_pos)
        self.highlight_keywords()
        return "break"

    def on_ctrl_backspace(self, event):
        text_widget = event.widget
        insert_pos = text_widget.index(tk.INSERT)
        line, col = map(int, insert_pos.split('.'))
        
        if col == 0:
            if line > 1:
                prev_line_end = text_widget.index(f"{line-1}.end")
                text_widget.delete(prev_line_end, insert_pos)
            self.highlight_keywords()
            return "break"
            
        line_text = text_widget.get(f"{line}.0", insert_pos)
        if not line_text:
            return "break"
            
        delete_len = 0
        rev_text = line_text[::-1]
        first_char = rev_text[0]
        
        if first_char.isspace():
            while delete_len < len(rev_text) and rev_text[delete_len].isspace():
                delete_len += 1
        elif first_char == '_':
            delete_len = 1
        elif first_char.isalnum():
            while delete_len < len(rev_text) and rev_text[delete_len].isalnum():
                if rev_text[delete_len] == '_':
                    break
                delete_len += 1
        else:
            delete_len = 1
            
        start_pos = f"{line}.{col - delete_len}"
        text_widget.delete(start_pos, insert_pos)
        self.highlight_keywords()
        return "break"

    def get_suggestions(self, word):
        word_lower = word.lower()
        suggestions = []
        for kw in self.sql_keywords:
            if kw.lower().startswith(word_lower):
                suggestions.append(kw)
        for t in self.all_tables:
            if t.lower().startswith(word_lower):
                suggestions.append(t)
        for c in self.all_columns:
            if c.lower().startswith(word_lower):
                suggestions.append(c)
        
        seen = set()
        unique_sug = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique_sug.append(s)
                
        return unique_sug[:15]

    def on_sql_ctrl_enter(self, event):
        self.execute_raw_sql()
        return "break"

    def load_tables(self):
        self.table_listbox.delete(0, tk.END)
        self.all_tables = []
        self.all_columns = set()
        
        success, rows, cols, err, count = self.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        )
        if not success:
            messagebox.showerror("Database Error", f"Failed to load tables:\n{err}")
            return
            
        for row in rows:
            t_name = row["name"]
            self.table_listbox.insert(tk.END, t_name)
            self.all_tables.append(t_name)
            
            sub_success, col_rows, _, _, _ = self.execute_query(f"PRAGMA table_info({t_name});")
            if sub_success:
                for col in col_rows:
                    self.all_columns.add(col["name"])

    def on_table_select(self, event):
        selection = self.table_listbox.curselection()
        if not selection:
            return
        self.current_table = self.table_listbox.get(selection[0])
        self.load_table_schema()
        self.load_table_data()

    def load_table_schema(self):
        if not self.current_table: return
        success, rows, cols, err, count = self.execute_query(f"PRAGMA table_info({self.current_table});")
        if not success:
            messagebox.showerror("Database Error", f"Failed to load schema:\n{err}")
            return
            
        self.columns = []
        self.primary_keys = []
        
        schema_str = "CID | Name | Type | NotNull | Default | PK\n"
        schema_str += "-"*50 + "\n"
        
        for col in rows:
            cid, name, ctype, notnull, dflt_value, pk = col["cid"], col["name"], col["type"], col["notnull"], col["dflt_value"], col["pk"]
            schema_str += f"{cid:3} | {name:15} | {ctype:10} | {notnull} | {dflt_value} | {pk}\n"
            self.columns.append(name)
            if pk > 0:
                self.primary_keys.append(name)
        
        self.schema_text.config(state=tk.NORMAL)
        self.schema_text.delete(1.0, tk.END)
        self.schema_text.insert(tk.END, schema_str)
        self.schema_text.config(state=tk.DISABLED)

        self.data_tree.delete(*self.data_tree.get_children())
        self.data_tree["columns"] = self.columns
        for col in self.columns:
            self.data_tree.heading(col, text=col)
            self.data_tree.column(col, width=100, anchor=tk.W)

    def load_table_data(self):
        if not self.current_table: return
        success, rows, cols, err, count = self.execute_query(f"SELECT * FROM {self.current_table} LIMIT 1000;")
        if not success:
            messagebox.showerror("Database Error", f"Failed to load data:\n{err}")
            return
            
        self.data_tree.delete(*self.data_tree.get_children())
        for row in rows:
            values = ["" if row[col] is None else row[col] for col in self.columns]
            self.data_tree.insert("", tk.END, values=values)

    def insert_record(self):
        if not self.current_table:
            messagebox.showwarning("Warning", "Please select a table first.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Insert into {self.current_table}")
        dialog.geometry("400x500")
        dialog.transient(self.root)
        dialog.grab_set()

        canvas = tk.Canvas(dialog)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        entries = {}
        row_idx = 0
        for col in self.columns:
            ttk.Label(scrollable_frame, text=col).grid(row=row_idx, column=0, padx=5, pady=5, sticky=tk.W)
            entry = ttk.Entry(scrollable_frame, width=30)
            entry.grid(row=row_idx, column=1, padx=5, pady=5, sticky=tk.EW)
            entries[col] = entry
            row_idx += 1

        def do_insert():
            cols_to_insert = []
            vals_to_insert = []
            for col, entry in entries.items():
                val = entry.get()
                if val != "":
                    cols_to_insert.append(col)
                    vals_to_insert.append(val)
            
            if not cols_to_insert:
                messagebox.showerror("Error", "No data provided.")
                return

            placeholders = ", ".join(["?"] * len(cols_to_insert))
            col_names = ", ".join(cols_to_insert)
            query = f"INSERT INTO {self.current_table} ({col_names}) VALUES ({placeholders})"

            success, _, _, err, count = self.execute_query(query, vals_to_insert, commit=True)
            if success:
                dialog.destroy()
                self.load_table_data()
                messagebox.showinfo("Success", "Record inserted successfully.")
            else:
                messagebox.showerror("Database Error", f"Failed to insert record:\n{err}")

        ttk.Button(scrollable_frame, text="Insert", command=do_insert).grid(row=row_idx, column=0, columnspan=2, pady=10)

    def update_record(self):
        selected = self.data_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a record to update.")
            return
        
        if not self.primary_keys:
            messagebox.showerror("Error", "Cannot update table without Primary Key.")
            return

        item = self.data_tree.item(selected[0])
        values = item['values']

        pk_values = {}
        for pk in self.primary_keys:
            pk_idx = self.columns.index(pk)
            pk_values[pk] = values[pk_idx]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Update record in {self.current_table}")
        dialog.geometry("400x500")
        dialog.transient(self.root)
        dialog.grab_set()

        canvas = tk.Canvas(dialog)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        entries = {}
        row_idx = 0
        for i, col in enumerate(self.columns):
            ttk.Label(scrollable_frame, text=col).grid(row=row_idx, column=0, padx=5, pady=5, sticky=tk.W)
            entry = ttk.Entry(scrollable_frame, width=30)
            
            val = values[i]
            if val is None:
                val = ""
            entry.insert(0, str(val))
            
            if col in self.primary_keys:
                entry.config(state=tk.DISABLED)
                
            entry.grid(row=row_idx, column=1, padx=5, pady=5, sticky=tk.EW)
            entries[col] = entry
            row_idx += 1

        def do_update():
            update_cols = []
            update_vals = []
            for col, entry in entries.items():
                if col not in self.primary_keys:
                    val = entry.get()
                    update_cols.append(f"{col} = ?")
                    update_vals.append(val)

            if not update_cols:
                dialog.destroy()
                return

            where_clauses = [f"{pk} = ?" for pk in self.primary_keys]
            where_vals = [pk_values[pk] for pk in self.primary_keys]

            query = f"UPDATE {self.current_table} SET {', '.join(update_cols)} WHERE {' AND '.join(where_clauses)}"
            params = update_vals + where_vals

            success, _, _, err, count = self.execute_query(query, params, commit=True)
            if success:
                dialog.destroy()
                self.load_table_data()
                messagebox.showinfo("Success", f"Record updated successfully. ({count} row(s) affected)")
            else:
                messagebox.showerror("Database Error", f"Failed to update record:\n{err}")

        ttk.Button(scrollable_frame, text="Update", command=do_update).grid(row=row_idx, column=0, columnspan=2, pady=10)

    def delete_record(self):
        selected = self.data_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a record to delete.")
            return

        if not self.primary_keys:
            messagebox.showerror("Error", "Cannot delete from table without Primary Key.")
            return

        if not messagebox.askyesno("Confirm Delete", "Are you sure you want to delete the selected record?"):
            return

        item = self.data_tree.item(selected[0])
        values = item['values']

        where_clauses = []
        where_vals = []
        for pk in self.primary_keys:
            pk_idx = self.columns.index(pk)
            where_clauses.append(f"{pk} = ?")
            where_vals.append(values[pk_idx])

        query = f"DELETE FROM {self.current_table} WHERE {' AND '.join(where_clauses)}"

        success, _, _, err, count = self.execute_query(query, where_vals, commit=True)
        if success:
            self.load_table_data()
            messagebox.showinfo("Success", f"Record deleted successfully. ({count} row(s) affected)")
        else:
            messagebox.showerror("Database Error", f"Failed to delete record:\n{err}")

    def get_query_at_cursor(self):
        try:
            selected_text = self.sql_text.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
            if selected_text:
                return selected_text
        except tk.TclError:
            pass

        content = self.sql_text.get(1.0, tk.END)
        cursor_idx = self.sql_text.index(tk.INSERT)
        line, col = map(int, cursor_idx.split('.'))
        
        lines = content.split('\n')
        cursor_offset = sum(len(l) + 1 for l in lines[:line - 1]) + col

        queries = []
        current_query = []
        start_offset = 0
        in_string = False
        string_char = None
        
        for i, char in enumerate(content):
            current_query.append(char)
            if char in ("'", '"') and (i == 0 or content[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
                    
            if char == ';' and not in_string:
                queries.append((''.join(current_query), start_offset, i + 1))
                current_query = []
                start_offset = i + 1
                
        if current_query:
            queries.append((''.join(current_query), start_offset, len(content)))

        for q_text, start, end in queries:
            if start <= cursor_offset <= end:
                return q_text.strip()
                
        return content.strip()

    def execute_raw_sql(self):
        query = self.get_query_at_cursor()
        if not query:
            messagebox.showwarning("Warning", "Please enter a SQL query.")
            return

        success, result, cols, err, count = self.execute_query(query, commit=True)
        if not success:
            messagebox.showerror("Database Error", f"Failed to execute query:\n{err}")
            return

        if cols is not None:
            self.data_tree.delete(*self.data_tree.get_children())
            self.data_tree["columns"] = cols
            for col in cols:
                self.data_tree.heading(col, text=col)
                self.data_tree.column(col, width=100, anchor=tk.W)
            
            for row in result:
                values = ["" if row[col] is None else row[col] for col in cols]
                self.data_tree.insert("", tk.END, values=values)
                
            messagebox.showinfo("Result", f"Query executed successfully. ({count} row(s) returned)")
        else:
            messagebox.showinfo("Result", f"Query executed successfully. {count} row(s) affected.")
            if self.current_table:
                self.load_table_data()

if __name__ == "__main__":
    root = tk.Tk()
    app = DBInspectorApp(root)
    root.mainloop()
