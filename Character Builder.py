#!/usr/bin/env python3
"""
Character Builder
=================
A local fantasy novel world-building and character tracker.

- Pure desktop app: customTkinter GUI + built-in sqlite3. No server, no internet.
- Database:  ./Character.sqlite  (created automatically on first run)
- Images:    ./images/           (put hero.png etc. here, then type "hero.png" in Edit mode)

Install:  pip install customtkinter pillow
Run:      python app.py

Keyboard navigation (no global hotkeys, so typing is never intercepted)
-----------------------------------------------------------------------
Search box: Enter opens the first match and focuses the Edit button.
Sidebar list: Up/Down to browse, Enter to open (focus jumps to Edit).
Buttons: Tab to them and press Enter (or Space).
"""

import re
import shutil
import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

# --------------------------------------------------------------------------- #
# Paths & constants
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "Character.sqlite"         # default profile
LEGACY_DB_PATH = BASE_DIR / "database.sqlite"   # older default; used only if Character.sqlite is missing
LAST_PROFILE_FILE = BASE_DIR / "last_profile.txt"  # remembers the last profile
IMAGE_DIR = BASE_DIR / "images"
ENTITY_TYPES = ["Character", "Place"]
FIELD_TYPES = ["text", "textarea", "list"]

# =========================================================================== #
# THEME  -  "Emerald Hollow"
# --------------------------------------------------------------------------- #
# Every colour below comes from the seven swatches sampled from Theme.jpg, or is
# a tint/shade of one of them (noted beside each value). Contrast ratios were
# checked for every text/background pairing used in the app (WCAG: 4.5:1 for
# text, 3:1 for outlines).
#
#   ROLE                       SWATCH
#   structure & primary action COPPER     gilt rules, diamonds, primary buttons
#   interaction & selection    JADE       selection, tags, secondary outlines
#   depth                      CHARCOAL > FOREST > SLATE / PINE   (back to front)
#   quiet text and lines       ASH
# =========================================================================== #

# --- 1. Source swatches (sampled from Theme.jpg) ---------------------------- #
SW_JADE = "#4D7A63"
SW_FOREST = "#1F302A"
SW_PINE = "#374E46"
SW_COPPER = "#A77646"
SW_SLATE = "#363E40"
SW_CHARCOAL = "#151918"
SW_ASH = "#6B6F6E"

# --- 2. Surfaces: darkest at the back, lighter toward the reader ------------ #
WINDOW_BG = SW_CHARCOAL          # behind everything
SIDEBAR_BG = SW_FOREST           # navigation
PANEL_BG = "#1C2824"             # modal panels      (forest, deepened toward charcoal)
SURFACE = SW_SLATE               # the entry card
SURFACE_RAISED = SW_PINE         # rows resting on a panel
INPUT_BG = "#222828"             # inset text fields (charcoal lifted toward slate)

# --- 3. Lines --------------------------------------------------------------- #
BORDER = "#4E5455"               # hairlines          (slate toward ash)
BORDER_STRONG = "#979A9A"        # input outlines     (ash, lightened)
BORDER_GILT = "#745D43"          # dim gilt frame     (copper toward slate)

# --- 4. Type ----------------------------------------------------------------- #
TEXT = "#EDEEEE"                 # body              (ash, near white)
TEXT_DISPLAY = "#EFE6DE"         # titles            (copper, near white: warm ivory)
TEXT_MUTED = "#C4C5C5"           # captions, hints   (ash, lightened)
TEXT_LABEL = "#AFC3B9"           # field names       (jade, lightened)
TEXT_HEADING = "#C8AA8C"         # section headings  (copper, lightened)
TEXT_ON_ACCENT = "#0A0C0C"       # text on copper    (charcoal, deepened)

# --- 5. Accent and state colours ----------------------------------------------- #
ACCENT = SW_COPPER               # primary buttons, ornaments, drop indicator
ACCENT_HOVER = "#B38960"         # copper, lightened
SELECTION_BG = "#3B5C4C"         # selected entry and tags   (jade, deepened)
SECONDARY_EDGE = "#82A292"       # secondary outlines        (jade, lightened)
HOVER_BG = "#2D423B"             # hover wash                (forest toward pine)
DANGER = "#F5A898"               # destructive actions       (soft coral)
FOCUS_RING = TEXT_DISPLAY        # keyboard focus
DRAG_BG = "#645E46"              # row held while dragging   (pine toward copper)
SCROLL_THUMB = "#535959"         # scrollbars                (ash toward slate)

# --- 6. Typography ---------------------------------------------------------------- #
# The first installed family in each list is used (see resolve_fonts). Installing
# the free "Cinzel" font gives titles an inscribed, fantasy look.
FONT_DISPLAY_CANDIDATES = ["Cinzel", "Marcellus", "Trajan Pro", "Palatino Linotype",
                           "Book Antiqua", "Palatino", "Georgia", "DejaVu Serif"]
FONT_BODY_CANDIDATES = ["Palatino Linotype", "Book Antiqua", "Palatino", "Georgia",
                        "Cambria", "DejaVu Serif", "Times New Roman"]
FONTS = {"display": "Georgia", "body": "Georgia"}   # filled in by resolve_fonts()

# category -> list of (field name, multiline?)
SEED_FIELDS = [
    ("Description", [("Description", True)]),
    ("Relations", [
        ("Best friend", False), ("Enemies", False), ("Raised by", False),
    ]),
    ("Musical Contributions", [
        ("Instruments", False), ("Want to learn", False),
    ]),
    ("Dances", [
        ("Ritual related", False), ("Free form", False),
    ]),
    ("Favorites", [
        ("Color", False), ("Food", False), ("Drink", False),
        ("Type of soup", False), ("Animal", False), ("Plant", False),
    ]),
]


# --------------------------------------------------------------------------- #
# Database layer
# --------------------------------------------------------------------------- #
class Database:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()
        self._migrate()
        self._seed_if_empty()
        self._sync_categories()

    def _init_schema(self):
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS entities (
                    id     INTEGER PRIMARY KEY AUTOINCREMENT,
                    name   TEXT NOT NULL,
                    type   TEXT NOT NULL DEFAULT 'Character',
                    image  TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS fields (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    category   TEXT NOT NULL COLLATE NOCASE,
                    name       TEXT NOT NULL COLLATE NOCASE,
                    multiline  INTEGER NOT NULL DEFAULT 0,
                    field_type TEXT NOT NULL DEFAULT 'text',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (category, name)
                );
                CREATE TABLE IF NOT EXISTS field_values (
                    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                    field_id  INTEGER NOT NULL REFERENCES fields(id)   ON DELETE CASCADE,
                    value     TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (entity_id, field_id)
                );
                CREATE TABLE IF NOT EXISTS categories (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    sort_order INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def _migrate(self):
        """Upgrade databases made by earlier versions (adds fields.field_type)."""
        cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(fields)")]
        if "field_type" not in cols:
            with self.conn:
                self.conn.execute(
                    "ALTER TABLE fields ADD COLUMN field_type TEXT NOT NULL DEFAULT 'text'")
                self.conn.execute(
                    "UPDATE fields SET field_type = 'textarea' WHERE multiline = 1")

    def _sync_categories(self):
        """Make sure every category used by a field exists in the categories table."""
        known = {r["name"].lower() for r in self.conn.execute("SELECT name FROM categories")}
        top = self.conn.execute("SELECT MAX(sort_order) FROM categories").fetchone()[0]
        next_order = 0 if top is None else top + 1
        used = self.conn.execute(
            "SELECT category, MIN(sort_order) AS m FROM fields GROUP BY category ORDER BY m"
        ).fetchall()
        with self.conn:
            for r in used:
                if r["category"].lower() not in known:
                    self.conn.execute(
                        "INSERT INTO categories (name, sort_order) VALUES (?, ?)",
                        (r["category"], next_order),
                    )
                    known.add(r["category"].lower())
                    next_order += 1

    def _seed_if_empty(self):
        count = self.conn.execute("SELECT COUNT(*) FROM fields").fetchone()[0]
        if count:
            return
        with self.conn:
            for cat_index, (category, items) in enumerate(SEED_FIELDS):
                for i, (name, multiline) in enumerate(items):
                    self.conn.execute(
                        "INSERT INTO fields (category, name, multiline, field_type, sort_order) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (category, name, int(multiline),
                         "textarea" if multiline else "text", cat_index * 100 + i),
                    )

    # ---- entities ---------------------------------------------------------
    def search_entities(self, query: str = ""):
        query = query.strip()
        if not query:
            return self.conn.execute(
                "SELECT id, name, type, image FROM entities ORDER BY name COLLATE NOCASE"
            ).fetchall()
        like = f"%{query}%"
        return self.conn.execute(
            """
            SELECT DISTINCT e.id, e.name, e.type, e.image
            FROM entities e
            LEFT JOIN field_values v ON v.entity_id = e.id
            WHERE e.name LIKE ? OR e.type LIKE ? OR v.value LIKE ?
            ORDER BY e.name COLLATE NOCASE
            """,
            (like, like, like),
        ).fetchall()

    def get_entity(self, entity_id):
        return self.conn.execute(
            "SELECT id, name, type, image FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()

    def save_entity(self, entity_id, name, etype, image, values):
        """Insert or update an entity and its field values. Returns the entity id."""
        with self.conn:
            if entity_id is None:
                cur = self.conn.execute(
                    "INSERT INTO entities (name, type, image) VALUES (?, ?, ?)",
                    (name, etype, image),
                )
                entity_id = cur.lastrowid
            else:
                self.conn.execute(
                    "UPDATE entities SET name = ?, type = ?, image = ? WHERE id = ?",
                    (name, etype, image, entity_id),
                )
            for field_id, value in values.items():
                if value:
                    self.conn.execute(
                        "INSERT INTO field_values (entity_id, field_id, value) "
                        "VALUES (?, ?, ?) "
                        "ON CONFLICT(entity_id, field_id) DO UPDATE SET value = excluded.value",
                        (entity_id, field_id, value),
                    )
                else:
                    self.conn.execute(
                        "DELETE FROM field_values WHERE entity_id = ? AND field_id = ?",
                        (entity_id, field_id),
                    )
        return entity_id

    def delete_entity(self, entity_id):
        with self.conn:
            self.conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))

    # ---- fields -----------------------------------------------------------
    def get_fields(self):
        """All fields grouped by category (category order, then field order)."""
        return self.conn.execute(
            """
            SELECT f.id, COALESCE(c.name, f.category) AS category, f.name,
                   f.multiline, f.field_type, f.sort_order
            FROM fields f
            LEFT JOIN categories c ON c.name = f.category
            ORDER BY COALESCE(c.sort_order, 1000000), f.category, f.sort_order, f.id
            """
        ).fetchall()

    def get_categories(self):
        """All categories in display order, including ones with no fields."""
        rows = self.conn.execute(
            "SELECT name FROM categories ORDER BY sort_order, id").fetchall()
        return [r["name"] for r in rows]

    def get_values(self, entity_id):
        rows = self.conn.execute(
            "SELECT field_id, value FROM field_values WHERE entity_id = ?", (entity_id,)
        ).fetchall()
        return {r["field_id"]: r["value"] for r in rows}

    def count_values(self, field_ids):
        """How many saved entity values belong to these fields."""
        field_ids = list(field_ids)
        if not field_ids:
            return 0
        marks = ",".join("?" * len(field_ids))
        return self.conn.execute(
            f"SELECT COUNT(*) FROM field_values WHERE field_id IN ({marks})", field_ids
        ).fetchone()[0]

    def apply_field_layout(self, categories, fields, deletes):
        """
        Save the whole Adjust Fields layout in ONE transaction (all or nothing).
          categories: [name, ...] in display order (empty categories included)
          fields:     [{"id" (None = new), "name", "category", "field_type",
                        "sort_order"}, ...]
          deletes:    [field_id, ...]  (their saved values are removed too)
        A category can only disappear if no field still uses it.
        """
        with self.conn:
            for fid in deletes:
                # Explicit cleanup, in addition to ON DELETE CASCADE
                self.conn.execute("DELETE FROM field_values WHERE field_id = ?", (fid,))
                self.conn.execute("DELETE FROM fields WHERE id = ?", (fid,))

            existing = [f for f in fields if f["id"] is not None]
            # Park edited rows on temporary names first so swapping two names
            # can't trip the UNIQUE(category, name) constraint mid-way.
            for f in existing:
                self.conn.execute("UPDATE fields SET name = ? WHERE id = ?",
                                  (f"__tmp_{f['id']}__", f["id"]))
            for f in existing:
                self.conn.execute(
                    "UPDATE fields SET name = ?, category = ?, field_type = ?, "
                    "multiline = ?, sort_order = ? WHERE id = ?",
                    (f["name"], f["category"], f["field_type"],
                     int(f["field_type"] == "textarea"), f["sort_order"], f["id"]),
                )
            for f in fields:
                if f["id"] is None:
                    self.conn.execute(
                        "INSERT INTO fields (category, name, multiline, field_type, sort_order) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (f["category"], f["name"], int(f["field_type"] == "textarea"),
                         f["field_type"], f["sort_order"]),
                    )

            for order, name in enumerate(categories):
                cur = self.conn.execute(
                    "UPDATE categories SET sort_order = ? WHERE name = ?", (order, name))
                if cur.rowcount == 0:
                    self.conn.execute(
                        "INSERT INTO categories (name, sort_order) VALUES (?, ?)",
                        (name, order))
            if categories:
                marks = ",".join("?" * len(categories))
                self.conn.execute(
                    f"DELETE FROM categories WHERE name NOT IN ({marks})", list(categories))
            else:
                self.conn.execute("DELETE FROM categories")

            orphans = self.conn.execute(
                "SELECT COUNT(*) FROM fields "
                "WHERE category NOT IN (SELECT name FROM categories)").fetchone()[0]
            if orphans:  # raising inside the transaction rolls everything back
                raise sqlite3.IntegrityError(
                    "A category can't be removed while fields are still assigned to it.")

    def close(self):
        self.conn.close()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_focusable(button, key_command=None):
    """
    CTkButtons aren't keyboard-focusable by default. This makes the button a Tab
    stop, shows a dark focus ring, and lets Enter / Space activate it.
    """
    try:
        canvas = button._canvas
        base_width = button.cget("border_width")
        base_color = button.cget("border_color")
        canvas.configure(takefocus=1)

        def on_focus_in(_e):
            try:
                button.configure(border_width=max(base_width, 3), border_color=FOCUS_RING)
            except tk.TclError:
                pass

        def on_focus_out(_e):
            try:
                button.configure(border_width=base_width, border_color=base_color)
            except tk.TclError:
                pass

        def on_key(_e):
            cmd = key_command or button.cget("command")
            if cmd:
                cmd()
            return "break"

        def on_next(_e):
            canvas.tk_focusNext().focus_set()
            return "break"

        def on_prev(_e):
            canvas.tk_focusPrev().focus_set()
            return "break"

        canvas.bind("<FocusIn>", on_focus_in)
        canvas.bind("<FocusOut>", on_focus_out)
        for seq in ("<Return>", "<KP_Enter>", "<space>"):
            canvas.bind(seq, on_key)
        canvas.bind("<Down>", on_next)
        canvas.bind("<Up>", on_prev)
    except Exception:
        pass  # worst case: button is mouse-only


# --------------------------------------------------------------------------- #
# Shared style helpers (themed widgets and ornaments)
# --------------------------------------------------------------------------- #
def resolve_fonts():
    """Pick the best installed families. Needs a Tk root window to exist."""
    try:
        from tkinter import font as tkfont
        installed = {name.lower() for name in tkfont.families()}
    except Exception:
        return

    def pick(candidates, default):
        for name in candidates:
            if name.lower() in installed:
                return name
        return default

    FONTS["body"] = pick(FONT_BODY_CANDIDATES, "Times")
    FONTS["display"] = pick(FONT_DISPLAY_CANDIDATES, FONTS["body"])


def font(size=15, weight="normal", slant="roman", display=False):
    return ctk.CTkFont(family=FONTS["display" if display else "body"], size=size,
                       weight=weight, slant=slant)


def primary_button(parent, text, command, width=96, height=38):
    btn = ctk.CTkButton(
        parent, text=text, width=width, height=height, corner_radius=4,
        fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT_ON_ACCENT,
        font=font(14, "bold", display=True), command=command,
    )
    make_focusable(btn)
    return btn


def secondary_button(parent, text, command, width=96, height=38, danger=False):
    color = DANGER if danger else TEXT
    btn = ctk.CTkButton(
        parent, text=text, width=width, height=height, corner_radius=4,
        fg_color="transparent", hover_color=HOVER_BG, text_color=color,
        border_width=1, border_color=DANGER if danger else SECONDARY_EDGE,
        font=font(15), command=command,
    )
    make_focusable(btn)
    return btn


def styled_entry(parent, height=38, **kw):
    return ctk.CTkEntry(
        parent, height=height, corner_radius=4, fg_color=INPUT_BG, text_color=TEXT,
        placeholder_text_color=BORDER_STRONG, border_color=BORDER_STRONG,
        border_width=1, font=font(15), **kw)


def styled_combo(parent, values, height=38, **kw):
    return ctk.CTkComboBox(
        parent, values=values, state="readonly", height=height, corner_radius=4,
        fg_color=INPUT_BG, text_color=TEXT, border_color=BORDER_STRONG, border_width=1,
        button_color=SELECTION_BG, button_hover_color=SW_JADE,
        dropdown_fg_color=INPUT_BG, dropdown_text_color=TEXT,
        dropdown_hover_color=SELECTION_BG, font=font(15), dropdown_font=font(14), **kw)


def styled_textbox(parent, height=110, **kw):
    return ctk.CTkTextbox(
        parent, height=height, corner_radius=4, fg_color=INPUT_BG, text_color=TEXT,
        border_color=BORDER_STRONG, border_width=1, font=font(15), wrap="word", **kw)


def scrollable(parent, fg=SURFACE, **kw):
    return ctk.CTkScrollableFrame(
        parent, fg_color=fg, corner_radius=0, scrollbar_fg_color=fg,
        scrollbar_button_color=SCROLL_THUMB, scrollbar_button_hover_color=SW_JADE, **kw)


def ornament(parent, color=ACCENT):
    """A thin gilt rule with a small diamond at its centre."""
    frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0, height=16)
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_columnconfigure(2, weight=1)
    ctk.CTkFrame(frame, height=1, fg_color=color, corner_radius=0).grid(
        row=0, column=0, sticky="ew")
    ctk.CTkLabel(frame, text="\u25C6", font=font(12), text_color=color).grid(
        row=0, column=1, padx=12)
    ctk.CTkFrame(frame, height=1, fg_color=color, corner_radius=0).grid(
        row=0, column=2, sticky="ew")
    return frame


def section_header(parent, text, size=15):
    """Diamond, engraved capitals, and a dim gilt rule running to the edge."""
    frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
    frame.grid_columnconfigure(2, weight=1)
    ctk.CTkLabel(frame, text="\u25C6", font=font(11), text_color=ACCENT).grid(
        row=0, column=0, padx=(0, 10))
    ctk.CTkLabel(frame, text=text.upper(), font=font(size, "bold", display=True),
                 text_color=TEXT_HEADING).grid(row=0, column=1)
    ctk.CTkFrame(frame, height=1, fg_color=BORDER_GILT, corner_radius=0).grid(
        row=0, column=2, sticky="ew", padx=(14, 0))
    return frame


def build_plain_text(db: Database, entity_id) -> str:
    """
    Plain text with EVERY category and field, empty ones included:

        Category Name
        Field Name: Field Value
        Empty Field Name:

        Category Name
        Field Name: Field Value
    """
    ent = db.get_entity(entity_id)
    if ent is None:
        return ""
    values = db.get_values(entity_id)

    groups = {}
    for f in db.get_fields():
        v = (values.get(f["id"]) or "").strip()
        if f["field_type"] == "list":
            v = ", ".join(i.strip() for i in v.splitlines() if i.strip())
        line = f"{f['name']}: {v}" if v else f"{f['name']}:"
        groups.setdefault(f["category"], []).append(line)

    blocks = ["\n".join([category] + lines) for category, lines in groups.items()]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


GENERIC_PROFILE_NAMES = {"database", "db", "data", "profile", "app", "new",
                         "untitled", "default"}


def profile_noun(path):
    """
    Singular noun for the entries in a profile, taken from its file name:
    characters.sqlite -> Character, places.sqlite -> Place,
    factions.sqlite -> Faction, database.sqlite -> Entry.
    """
    stem = Path(path).stem
    low = stem.lower()
    if "character" in low:
        return "Character"
    if "place" in low or "location" in low:
        return "Place"
    words = [w for w in re.split(r"[\s_\-.]+", stem) if w]
    if not words or low in GENERIC_PROFILE_NAMES:
        return "Entry"
    last = words[-1].lower()
    if last.endswith("ies") and len(last) > 3:
        last = last[:-3] + "y"
    elif last.endswith(("ches", "shes", "sses", "xes", "zes")):
        last = last[:-2]
    elif last.endswith("s") and not last.endswith("ss") and len(last) > 1:
        last = last[:-1]
    return " ".join([w.capitalize() for w in words[:-1]] + [last.capitalize()])


def check_profile_file(path):
    """Return None if `path` can be used as a profile, otherwise a reason it can't."""
    path = Path(path)
    if not path.is_file():
        return "That file doesn't exist."
    try:
        size = path.stat().st_size
        with open(path, "rb") as fh:
            header = fh.read(16)
    except OSError as exc:
        return f"Couldn't read that file: {exc}"
    if size == 0:
        return None                      # empty file: it will be set up on load
    if header != b"SQLite format 3\x00":
        return "That isn't a SQLite database file."
    try:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"Couldn't open that database: {exc}"
    tables = {t for t in tables if not t.startswith("sqlite_")}
    if not tables:
        return None                      # valid but empty database
    if not {"entities", "fields", "field_values"} <= tables:
        return ("That database wasn't made by Character Builder, so it hasn't been "
                "opened or changed.")
    return None


def startup_profile_path():
    """The profile used at launch: the last one loaded, else Character.sqlite."""
    try:
        last = Path(LAST_PROFILE_FILE.read_text(encoding="utf-8").strip())
        if last.is_file() and check_profile_file(last) is None:
            return last.resolve()
    except (OSError, ValueError):
        pass
    # Existing users: keep using the older database.sqlite until Character.sqlite exists,
    # so upgrading never makes saved entries look like they disappeared.
    if (not DB_PATH.exists() and LEGACY_DB_PATH.is_file()
            and check_profile_file(LEGACY_DB_PATH) is None):
        return LEGACY_DB_PATH
    return DB_PATH


def remember_profile(path):
    try:
        LAST_PROFILE_FILE.write_text(str(path), encoding="utf-8")
    except OSError:
        pass                              # not critical


# --------------------------------------------------------------------------- #
# Dialog windows
# --------------------------------------------------------------------------- #
class ExportWindow(ctk.CTkToplevel):
    def __init__(self, master, title, text):
        super().__init__(master)
        self.title(f"Export - {title}")
        self.geometry("780x680")
        self.minsize(520, 400)
        self.configure(fg_color=WINDOW_BG)
        self.transient(master)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Export", font=font(26, "bold", display=True),
                     text_color=TEXT_DISPLAY, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=32, pady=(26, 0))
        ctk.CTkLabel(
            self, text="Plain text \u2014 exactly what the Copy button copies",
            font=font(14, slant="italic"), text_color=TEXT_MUTED, anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 10))

        card = ctk.CTkFrame(self, fg_color=SURFACE, border_width=1,
                            border_color=BORDER_GILT, corner_radius=6)
        card.grid(row=2, column=0, sticky="nsew", padx=32, pady=4)
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)
        self.textbox = ctk.CTkTextbox(
            card, font=font(15), fg_color=SURFACE, text_color=TEXT, border_width=0,
            corner_radius=4, wrap="word")
        self.textbox.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        self.textbox.insert("1.0", text)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=32, pady=(14, 26))
        self.copy_btn = primary_button(bar, "Copy to Clipboard", self.copy, width=200)
        self.copy_btn.pack(side="left")
        secondary_button(bar, "Close", self.destroy, width=100).pack(side="right")

        self.after(150, self._finish_setup)

    def _finish_setup(self):
        try:
            self.lift()
            self.focus_force()
            self.copy_btn._canvas.focus_set()
        except tk.TclError:
            pass

    def copy(self):
        text = self.textbox.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()  # keep clipboard contents after the window closes
        self.copy_btn.configure(text="Copied \u2713")
        self.after(1500, lambda: self._reset_copy_label())

    def _reset_copy_label(self):
        try:
            self.copy_btn.configure(text="Copy to Clipboard")
        except tk.TclError:
            pass


def find_drop_target(y, blocks):
    """
    Where would a dragged field land if released at screen-y `y`?
    blocks: one dict per category, in on-screen order:
        {"header_bottom": y, "rows": [(top, bottom), ...], "end": y where this
         category's zone stops (top of the next header, or infinity)}
    Returns (category_index, insert_index), or None if there are no categories.
    """
    for ci, b in enumerate(blocks):
        if y < b["header_bottom"]:
            return ci, 0
        rows = b["rows"]
        if not rows:
            if y < b["end"]:
                return ci, 0
            continue
        for ri, (top, bottom) in enumerate(rows):
            if y < (top + bottom) / 2:
                return ci, ri
        if y < b["end"]:
            return ci, len(rows)
    if not blocks:
        return None
    return len(blocks) - 1, len(blocks[-1]["rows"])


def drop_line_y(target, blocks):
    """Screen-y where the drop indicator line should be drawn for a target."""
    ci, ri = target
    b = blocks[ci]
    if ri < len(b["rows"]):
        return b["rows"][ri][0]
    if b["rows"]:
        return b["rows"][-1][1]
    return b["header_bottom"]


class NameDialog(ctk.CTkToplevel):
    """Small modal that asks for a single name (used for new categories)."""

    def __init__(self, master, title, prompt, validate=None):
        super().__init__(master)
        self.result = None
        self._validate = validate
        self.title(title)
        self.geometry("460x230")
        self.resizable(False, False)
        self.configure(fg_color=WINDOW_BG)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        ctk.CTkLabel(self, text=prompt, font=font(17, "bold", display=True),
                     text_color=TEXT_DISPLAY, anchor="w").pack(
            padx=32, pady=(30, 10), anchor="w")
        self.entry = styled_entry(self, width=396)
        self.entry.pack(padx=32)
        self.entry.bind("<Return>", lambda _e: self.ok())

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=32, pady=24)
        primary_button(row, "OK", self.ok, width=100).pack(side="left")
        secondary_button(row, "Cancel", self.destroy, width=100).pack(side="left", padx=10)
        self.after(150, self._finish_setup)

    def _finish_setup(self):
        try:
            self.lift()
            self.grab_set()
            self.entry.focus_set()
        except tk.TclError:
            pass

    def ok(self):
        value = self.entry.get().strip()
        if not value:
            messagebox.showwarning("Name required", "Please enter a name.", parent=self)
            return
        error = self._validate(value) if self._validate else None
        if error:
            messagebox.showwarning("Can't use that name", error, parent=self)
            return
        self.result = value
        self.destroy()


def ask_name(parent, title, prompt, validate=None):
    dialog = NameDialog(parent, title, prompt, validate)
    parent.wait_window(dialog)
    return dialog.result


class AdjustFieldsWindow(ctk.CTkToplevel):
    """
    Global field manager (File > Adjust Fields).

    Fields are grouped under category sections. Drag a field's handle to reorder it
    or to move it into another category. Everything (categories, fields, order) is
    held in memory until "Save Changes" writes it to the database in one transaction.
    """

    W_TYPE, W_DEL = 110, 84

    def __init__(self, master, db, on_saved):
        super().__init__(master)
        self.db = db
        self.on_saved = on_saved
        self.cats = []          # [{"name": str, "fields": [rec, ...]}, ...]
        self.deleted_ids = []   # ids of existing fields removed locally
        self.cat_widgets = []   # per category: {"header": widget, "rows": [frames]}
        self._drag = None

        self.title("Adjust Fields")
        self.geometry("920x760")
        self.minsize(760, 500)
        self.configure(fg_color=WINDOW_BG)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text="Adjust Fields", font=font(28, "bold", display=True),
                     text_color=TEXT_DISPLAY, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=34, pady=(28, 4))
        ornament(self).grid(row=1, column=0, sticky="ew", padx=34, pady=(0, 8))
        ctk.CTkLabel(
            self,
            text=("Drag the \u2261 handle to reorder a field or move it to another category. "
                  "Nothing is saved until you press Save Changes. Deleting a field also "
                  "deletes its saved values for every entry. A category can only be "
                  "deleted when it has no fields."),
            font=font(13, slant="italic"), text_color=TEXT_MUTED, anchor="w",
            justify="left", wraplength=820,
        ).grid(row=2, column=0, sticky="ew", padx=34, pady=(0, 12))

        panel = ctk.CTkFrame(self, fg_color=PANEL_BG, border_width=1,
                             border_color=BORDER_GILT, corner_radius=6)
        panel.grid(row=3, column=0, sticky="nsew", padx=34, pady=4)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        self.list = scrollable(panel, PANEL_BG)
        self.list.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=12)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=34, pady=(14, 28))
        add_cat = secondary_button(footer, "+ Add Category", self.add_category, width=170)
        add_cat.pack(side="left")
        save = primary_button(footer, "Save Changes", self.save, width=160)
        save.pack(side="right")
        cancel = secondary_button(footer, "Cancel", self.cancel, width=100)
        cancel.pack(side="right", padx=10)

        self._load()
        self._render()
        self._initial = self._signature()
        self.after(150, self._finish_setup)

    def _finish_setup(self):
        try:
            self.lift()
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _regrab(self):
        """Re-take the modal grab after a child dialog closes."""
        try:
            self.grab_set()
        except tk.TclError:
            pass

    # ---- model ------------------------------------------------------------
    def _new_rec(self, field=None):
        name, kind, fid = "", "text", None
        if field is not None:
            name, fid = field["name"], field["id"]
            kind = field["field_type"] if field["field_type"] in FIELD_TYPES else "text"
        return {"id": fid, "name": tk.StringVar(self, value=name),
                "type": tk.StringVar(self, value=kind),
                "frame": None, "entry": None, "handle": None}

    def _load(self):
        by_cat = {}
        for f in self.db.get_fields():
            by_cat.setdefault(f["category"], []).append(f)
        for name in self.db.get_categories():
            self.cats.append({"name": name,
                              "fields": [self._new_rec(f) for f in by_cat.get(name, [])]})

    def _locate(self, rec):
        for ci, cat in enumerate(self.cats):
            for ri, r in enumerate(cat["fields"]):
                if r is rec:
                    return ci, ri
        return None

    def _signature(self):
        flat = []
        for cat in self.cats:
            for rec in cat["fields"]:
                flat.append((rec["id"], rec["name"].get().strip(), cat["name"],
                             rec["type"].get()))
        return (tuple(c["name"] for c in self.cats), tuple(flat),
                tuple(sorted(self.deleted_ids)))

    # ---- rendering -----------------------------------------------------------
    def _render(self):
        try:
            scroll_pos = self.list._parent_canvas.yview()[0]
        except Exception:
            scroll_pos = 0.0

        for child in self.list.winfo_children():
            child.destroy()
        self.cat_widgets = []
        note_font = font(13, slant="italic")

        for ci, cat in enumerate(self.cats):
            header = ctk.CTkFrame(self.list, fg_color="transparent", corner_radius=0)
            header.pack(fill="x", pady=(26 if ci else 4, 4))
            header.grid_columnconfigure(2, weight=1)
            n = len(cat["fields"])
            ctk.CTkLabel(header, text="\u25C6", font=font(11), text_color=ACCENT).grid(
                row=0, column=0, padx=(8, 8))
            ctk.CTkLabel(header, text=cat["name"].upper(),
                         font=font(16, "bold", display=True), text_color=TEXT_HEADING,
                         anchor="w").grid(row=0, column=1, sticky="w")
            ctk.CTkLabel(header, text=f"{n} field{'s' if n != 1 else ''}", font=note_font,
                         text_color=TEXT_MUTED, anchor="w").grid(
                row=0, column=2, sticky="w", padx=14)
            del_cat = secondary_button(
                header, "Delete Category", lambda c=cat: self.delete_category(c),
                width=150, height=32, danger=True)
            del_cat.grid(row=0, column=3, padx=(0, 4))
            ctk.CTkFrame(header, height=1, fg_color=BORDER_GILT, corner_radius=0).grid(
                row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))

            rows = [self._build_row(rec) for rec in cat["fields"]]
            if not cat["fields"]:
                ctk.CTkLabel(self.list, text="No fields yet. Drag one here or add one below.",
                             font=note_font, text_color=TEXT_MUTED, anchor="w").pack(
                    fill="x", padx=16, pady=6)
            add = secondary_button(self.list, "+ Add Field",
                                   lambda c=cat: self.add_field(c), width=128, height=32)
            add.pack(anchor="w", padx=46, pady=(6, 0))
            self.cat_widgets.append({"header": header, "rows": rows})

        try:
            self.update_idletasks()
            self.list._parent_canvas.yview_moveto(scroll_pos)
        except Exception:
            pass

    def _build_row(self, rec):
        frame = ctk.CTkFrame(self.list, fg_color=SURFACE_RAISED, border_width=1,
                             border_color=BORDER, corner_radius=4)
        frame.pack(fill="x", pady=3)
        frame.grid_columnconfigure(1, weight=1)

        handle = tk.Label(frame, text="\u2261", font=(FONTS["body"], 20), bg=SURFACE_RAISED,
                          fg=SECONDARY_EDGE, cursor="fleur", padx=10)
        handle.grid(row=0, column=0, pady=6)
        handle.bind("<ButtonPress-1>", lambda e, r=rec: self._drag_start(e, r))
        handle.bind("<B1-Motion>", self._drag_motion)
        handle.bind("<ButtonRelease-1>", self._drag_end)

        entry = styled_entry(frame, height=34, textvariable=rec["name"])
        entry.grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        combo = styled_combo(frame, FIELD_TYPES, height=34, width=self.W_TYPE,
                             variable=rec["type"])
        combo.grid(row=0, column=2, padx=4, pady=6)
        delete = secondary_button(frame, "Delete", lambda r=rec: self._delete_field(r),
                                  width=self.W_DEL, height=34, danger=True)
        delete.grid(row=0, column=3, padx=(4, 10), pady=6)

        rec["frame"], rec["entry"], rec["handle"] = frame, entry, handle
        return frame

    def _scroll_to(self, widget):
        try:
            self.update_idletasks()
            canvas = self.list._parent_canvas
            total = max(1, self.list.winfo_height())
            first, last = canvas.yview()
            y = widget.winfo_y()
            if y < first * total or y + widget.winfo_height() > last * total:
                canvas.yview_moveto(max(0.0, (y - canvas.winfo_height() / 3) / total))
        except Exception:
            pass

    # ---- category actions ----------------------------------------------------
    def add_category(self):
        existing = {c["name"].lower() for c in self.cats}

        def check(value):
            if value.lower() in existing:
                return f"A category named \u201c{value}\u201d already exists."
            return None

        name = ask_name(self, "Add Category", "New category name", check)
        self._regrab()
        if not name:
            return
        self.cats.append({"name": name, "fields": []})
        self._render()
        try:
            self.update_idletasks()
            self.list._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def delete_category(self, cat):
        n = len(cat["fields"])
        if n:
            messagebox.showwarning(
                "Can't delete category",
                f"\u201c{cat['name']}\u201d still has {n} field{'s' if n != 1 else ''}. "
                "Move them to another category or delete them first.", parent=self)
            return
        self.cats = [c for c in self.cats if c is not cat]
        self._render()

    # ---- field actions --------------------------------------------------------
    def add_field(self, cat):
        rec = self._new_rec()
        cat["fields"].append(rec)
        self._render()
        self._scroll_to(rec["frame"])
        rec["entry"].focus_set()

    def _delete_field(self, rec):
        loc = self._locate(rec)
        if loc is None:
            return
        ci, _ri = loc
        cat = self.cats[ci]
        cat["fields"] = [r for r in cat["fields"] if r is not rec]
        if rec["id"] is not None:
            self.deleted_ids.append(rec["id"])   # removed from the DB on Save
        self._render()

    # ---- drag and drop ----------------------------------------------------------
    def _blocks(self):
        blocks = []
        count = len(self.cat_widgets)
        for ci, w in enumerate(self.cat_widgets):
            header = w["header"]
            nxt = (self.cat_widgets[ci + 1]["header"].winfo_rooty()
                   if ci + 1 < count else float("inf"))
            blocks.append({
                "header_bottom": header.winfo_rooty() + header.winfo_height(),
                "rows": [(f.winfo_rooty(), f.winfo_rooty() + f.winfo_height())
                         for f in w["rows"]],
                "end": nxt,
            })
        return blocks

    def _drag_start(self, event, rec):
        line = tk.Frame(self.list, bg=ACCENT_HOVER, height=4)
        self._drag = {"rec": rec, "target": None, "line": line}
        try:
            rec["frame"].configure(fg_color=DRAG_BG)
            rec["handle"].configure(bg=DRAG_BG)
        except tk.TclError:
            pass

    def _autoscroll(self, y):
        try:
            canvas = self.list._parent_canvas
            top = canvas.winfo_rooty()
            bottom = top + canvas.winfo_height()
            if y < top + 36:
                canvas.yview_scroll(-1, "units")
            elif y > bottom - 36:
                canvas.yview_scroll(1, "units")
        except Exception:
            pass

    def _drag_motion(self, event):
        if self._drag is None:
            return
        self._autoscroll(event.y_root)
        blocks = self._blocks()
        target = find_drop_target(event.y_root, blocks)
        self._drag["target"] = target
        line = self._drag["line"]
        if target is None:
            line.place_forget()
            return
        y = drop_line_y(target, blocks) - self.list.winfo_rooty()
        line.place(x=0, y=max(0, y - 2), relwidth=1.0, height=4)
        line.lift()

    def _drag_end(self, event):
        drag, self._drag = self._drag, None
        if drag is None:
            return
        try:
            drag["line"].destroy()
        except tk.TclError:
            pass
        rec, target = drag["rec"], drag["target"]
        if target is None:                      # a plain click, nothing moved
            try:
                rec["frame"].configure(fg_color=SURFACE_RAISED)
                rec["handle"].configure(bg=SURFACE_RAISED)
            except tk.TclError:
                pass
            return
        src = self._locate(rec)
        if src is not None:
            src_ci, src_ri = src
            self.cats[src_ci]["fields"].pop(src_ri)
            dest_ci, dest_ri = target
            if dest_ci == src_ci and dest_ri > src_ri:
                dest_ri -= 1                   # list shrank by one before the insert
            self.cats[dest_ci]["fields"].insert(dest_ri, rec)
        self._render()

    # ---- save / cancel ------------------------------------------------------------
    def _warn(self, message, widget):
        messagebox.showwarning("Check your fields", message, parent=self)
        try:
            widget.focus_set()
        except tk.TclError:
            pass

    def save(self):
        fields, seen, order = [], set(), 0
        for cat in self.cats:
            for rec in cat["fields"]:
                name = rec["name"].get().strip()
                if not name:
                    self._warn("Every field needs a name.", rec["entry"])
                    return
                key = (cat["name"].lower(), name.lower())
                if key in seen:
                    self._warn(f"There are two fields named \u201c{name}\u201d in "
                               f"\u201c{cat['name']}\u201d.", rec["entry"])
                    return
                seen.add(key)
                fields.append({"id": rec["id"], "name": name, "category": cat["name"],
                               "field_type": rec["type"].get(), "sort_order": order})
                order += 1

        if self._signature() == self._initial:   # nothing changed
            self.destroy()
            return

        deletes = list(self.deleted_ids)
        if deletes:
            count = self.db.count_values(deletes)
            detail = (f" and {count} saved value{'s' if count != 1 else ''}"
                      if count else "")
            if not messagebox.askyesno(
                    "Delete fields?",
                    f"Permanently delete {len(deletes)} field{'s' if len(deletes) != 1 else ''}"
                    f"{detail}? This can't be undone.", parent=self):
                return

        try:
            self.db.apply_field_layout([c["name"] for c in self.cats], fields, deletes)
        except sqlite3.Error as exc:
            messagebox.showerror("Couldn't save fields", str(exc), parent=self)
            return
        self.destroy()
        self.on_saved()

    def cancel(self):
        if self._signature() != self._initial and not messagebox.askyesno(
                "Discard changes?", "Discard your unsaved field changes?", parent=self):
            return
        self.destroy()


# --------------------------------------------------------------------------- #
# Main application
# --------------------------------------------------------------------------- #
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        resolve_fonts()   # choose installed families (needs the Tk root to exist)
        try:   # default family for any widget without an explicit font
            ctk.ThemeManager.theme["CTkFont"]["family"] = FONTS["body"]
        except Exception:
            pass

        IMAGE_DIR.mkdir(exist_ok=True)
        self.db_path = startup_profile_path()
        self.db = Database(self.db_path)
        self.noun = profile_noun(self.db_path)

        self.title(f"Character Builder - {self.db_path.name}")
        self.geometry("1120x780")
        self.minsize(840, 520)
        self.configure(fg_color=WINDOW_BG)

        # Fonts (must be created after the root window exists)
        self.f_title = font(34, "bold", display=True)   # card titles
        self.f_header = font(24, "bold", display=True)  # form headings
        self.f_body = font(16)                          # values and list entries
        self.f_label = font(15, slant="italic")         # field names
        self.f_small = font(12)

        # State
        self.selected_id = None
        self.editing = False
        self.edit_id = None
        self.list_buttons = {}
        self.field_widgets = {}   # field_id -> (widget, field_type)
        self.wrap_labels = []     # (label, width offset) for responsive wrapping
        self.edit_btn = None
        self._image_ref = None
        self._fields_window = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_menu()
        self._build_sidebar()

        self.main = ctk.CTkFrame(self, corner_radius=0, fg_color=WINDOW_BG)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)
        self.main.bind("<Configure>", self._on_resize)

        self.refresh_list()
        entities = self.db.search_entities("")
        if entities:
            self.select_entity(entities[0]["id"])
        else:
            self.show_empty()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- window plumbing ---------------------------------------------------
    def _build_menu(self):
        menu_style = dict(bg=SIDEBAR_BG, fg=TEXT, activebackground=SELECTION_BG,
                          activeforeground=TEXT_DISPLAY, relief="flat",
                          font=(FONTS["body"], 11))
        menubar = tk.Menu(self, **menu_style)
        file_menu = tk.Menu(menubar, tearoff=0, **menu_style)
        file_menu.add_command(label="Load Profile", command=self.load_profile)
        file_menu.add_command(label="New Profile", command=self.new_profile)
        file_menu.add_separator()
        file_menu.add_command(label="Adjust Fields", command=self.open_adjust_fields)
        menubar.add_cascade(label="File", menu=file_menu)
        self.configure(menu=menubar)

    # ---- profiles ------------------------------------------------------------------
    def _adjust_fields_open(self):
        win = self._fields_window
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_force()
            return True
        return False

    def load_profile(self):
        """File > Load Profile: switch to another SQLite database file."""
        if self._adjust_fields_open():
            return
        chosen = filedialog.askopenfilename(
            parent=self, title="Load Profile", initialdir=str(self.db_path.parent),
            filetypes=[("SQLite databases", "*.sqlite *.sqlite3 *.db"),
                       ("All files", "*.*")],
        )
        if chosen:
            self.switch_profile(Path(chosen))

    def new_profile(self):
        """File > New Profile: create an empty database (e.g. places.sqlite) and switch to it."""
        if self._adjust_fields_open():
            return
        chosen = filedialog.asksaveasfilename(
            parent=self, title="New Profile", initialdir=str(self.db_path.parent),
            defaultextension=".sqlite", initialfile="places.sqlite",
            filetypes=[("SQLite databases", "*.sqlite")],
        )
        if not chosen:
            return
        path = Path(chosen)
        if not path.exists():
            try:
                Database(path).close()    # creates the file with the starter fields
            except (sqlite3.Error, OSError) as exc:
                messagebox.showerror("Couldn't create profile", str(exc), parent=self)
                return
        self.switch_profile(path)

    def switch_profile(self, path):
        path = Path(path).resolve()
        if path == self.db_path:
            return
        if self.editing and not self.confirm_discard():
            return
        error = check_profile_file(path)
        if error:
            messagebox.showerror("Can't load profile", error, parent=self)
            return
        try:
            new_db = Database(path)       # sets up / upgrades the schema if needed
        except (sqlite3.Error, OSError) as exc:
            messagebox.showerror("Can't load profile", str(exc), parent=self)
            return

        old_db = self.db
        self.db, self.db_path = new_db, path
        try:
            old_db.close()
        except sqlite3.Error:
            pass
        remember_profile(path)

        self.editing = False
        self.edit_id = None
        self.selected_id = None
        self.noun = profile_noun(path)
        self.title(f"Character Builder - {path.name}")
        self.add_btn.configure(text=f"Add {self.noun}")
        self.profile_label.configure(text=path.stem)
        self.search_var.set("")
        self.refresh_list()
        entities = self.db.search_entities("")
        if entities:
            self.show_card(entities[0]["id"])
        else:
            self.show_empty()

    def default_entity_type(self):
        return self.noun if self.noun != "Entry" else ENTITY_TYPES[0]

    def open_adjust_fields(self):
        win = self._fields_window
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_force()
            return
        self._fields_window = AdjustFieldsWindow(self, self.db, self.after_fields_saved)

    def after_fields_saved(self):
        """Refresh whatever is on screen so new/changed/removed fields show up."""
        if self.editing:
            preset = self.collect_form()          # keep what was typed so far
            self.show_edit(self.edit_id, preset)
        elif self.selected_id is not None:
            self.show_card(self.selected_id)
        else:
            self.show_empty()

    def _on_close(self):
        try:
            self.db.close()
        finally:
            self.destroy()

    def _on_resize(self, event):
        for label, offset in list(self.wrap_labels):
            try:
                label.configure(wraplength=max(200, event.width - offset))
            except tk.TclError:
                pass

    # ---- sidebar -----------------------------------------------------------
    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=320, corner_radius=0, fg_color=SIDEBAR_BG)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(5, weight=1)
        # hairline between sidebar and card area
        ctk.CTkFrame(self.sidebar, width=1, corner_radius=0, fg_color=BORDER).place(
            relx=1.0, x=-1, y=0, relheight=1.0)

        ctk.CTkLabel(self.sidebar, text="Character Builder",
                     font=font(21, "bold", display=True), text_color=TEXT_DISPLAY,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=24, pady=(30, 0))
        self.profile_label = ctk.CTkLabel(
            self.sidebar, text=self.db_path.stem, font=font(13, slant="italic"),
            text_color=TEXT_MUTED, anchor="w")
        self.profile_label.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
        ornament(self.sidebar).grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_a: self.refresh_list())
        self.search_entry = styled_entry(self.sidebar, height=40, textvariable=self.search_var,
                                         placeholder_text="Search...")
        self.search_entry.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.search_entry.bind("<Return>", lambda _e: self._search_enter())

        self.add_btn = primary_button(self.sidebar, f"Add {self.noun}", self.add_entity,
                                      height=40)
        self.add_btn.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 14))

        self.list_frame = scrollable(self.sidebar, "transparent")
        self.list_frame.grid(row=5, column=0, sticky="nsew", padx=(14, 6), pady=(0, 16))
        self.list_frame.grid_columnconfigure(0, weight=1)

    def _search_enter(self):
        rows = self.db.search_entities(self.search_var.get())
        if rows:
            self.select_entity(rows[0]["id"], focus_edit=True)
        return "break"

    def refresh_list(self):
        for child in self.list_frame.winfo_children():
            child.destroy()
        self.list_buttons = {}

        rows = self.db.search_entities(self.search_var.get())
        if not rows:
            msg = "No matches." if self.search_var.get().strip() else "Nothing here yet."
            ctk.CTkLabel(self.list_frame, text=msg, font=font(14, slant="italic"),
                         text_color=TEXT_MUTED).grid(row=0, column=0, pady=24)
            return

        for i, row in enumerate(rows):
            glyph = {"Character": "\u2694", "Place": "\u2302"}.get(row["type"], "\u2022")
            btn = ctk.CTkButton(
                self.list_frame, text=f"{glyph}  {row['name']}", anchor="w", height=38,
                fg_color="transparent", text_color=TEXT, hover_color=HOVER_BG,
                font=self.f_body, corner_radius=4,
                command=lambda eid=row["id"]: self.select_entity(eid),
            )
            btn.grid(row=i, column=0, sticky="ew", pady=1, padx=2)
            make_focusable(btn, key_command=lambda eid=row["id"]: self.select_entity(
                eid, focus_edit=True))
            self.list_buttons[row["id"]] = btn
        self.highlight_selected()

    def highlight_selected(self):
        for eid, btn in self.list_buttons.items():
            try:
                if eid == self.selected_id:
                    btn.configure(fg_color=SELECTION_BG, text_color=TEXT_DISPLAY,
                                  hover_color=SELECTION_BG)
                else:
                    btn.configure(fg_color="transparent", text_color=TEXT, hover_color=HOVER_BG)
            except tk.TclError:
                pass

    # ---- navigation --------------------------------------------------------
    def confirm_discard(self):
        if not self.editing:
            return True
        return messagebox.askyesno("Discard changes?",
                                   "You're editing. Discard unsaved changes?", parent=self)

    def select_entity(self, entity_id, focus_edit=False):
        if self.editing and not self.confirm_discard():
            return
        self.show_card(entity_id)
        if focus_edit and self.edit_btn is not None:
            try:
                self.edit_btn._canvas.focus_set()
            except tk.TclError:
                pass

    def add_entity(self):
        if self.editing and not self.confirm_discard():
            return
        self.show_edit(None)

    # ---- shared widgets ----------------------------------------------------
    def clear_main(self):
        for child in self.main.winfo_children():
            child.destroy()
        self.wrap_labels = []
        self.field_widgets = {}
        self.edit_btn = None

    def _topbar(self):
        bar = ctk.CTkFrame(self.main, fg_color="transparent", corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew", padx=30, pady=(28, 12))
        return bar

    def _body(self):
        """The entry card: slate surface in a dim gilt frame, generous padding."""
        card = ctk.CTkFrame(self.main, fg_color=SURFACE, border_width=1,
                            border_color=BORDER_GILT, corner_radius=6)
        card.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 30))
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)
        body = scrollable(card, SURFACE)
        body.grid(row=0, column=0, sticky="nsew", padx=(32, 12), pady=(24, 16))
        body.grid_columnconfigure(0, weight=1)
        return body

    def _field_label(self, parent, text):
        return ctk.CTkLabel(parent, text=text, font=self.f_label, text_color=TEXT_LABEL,
                            anchor="w")

    def _button(self, parent, text, command, outline=False, danger=False, width=96):
        if outline or danger:
            return secondary_button(parent, text, command, width=width, danger=danger)
        return primary_button(parent, text, command, width=width)

    def _entry(self, parent, value=""):
        entry = styled_entry(parent)
        if value:
            entry.insert(0, value)
        return entry

    def _load_image(self, filename, max_side=320):
        if not filename:
            return None
        path = IMAGE_DIR / Path(filename).name  # never leave ./images/
        if not path.is_file():
            return None
        try:
            img = Image.open(path)
            img.load()
        except Exception:
            return None
        w, h = img.size
        scale = min(max_side / w, max_side / h, 2.0)
        size = (max(1, int(w * scale)), max(1, int(h * scale)))
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)

    # ---- empty view ----------------------------------------------------------
    def show_empty(self):
        self.editing = False
        self.selected_id = None
        self.clear_main()
        self.highlight_selected()
        holder = ctk.CTkFrame(self.main, fg_color=WINDOW_BG)
        holder.grid(row=0, column=0, rowspan=2, sticky="nsew")
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)
        inner = ctk.CTkFrame(holder, fg_color="transparent")
        inner.grid(row=0, column=0)
        ornament(inner).pack(fill="x", padx=40, pady=(0, 18))
        ctk.CTkLabel(
            inner,
            text=(f"Select {'an' if self.noun[0].lower() in 'aeiou' else 'a'} "
                  f"{self.noun.lower()} on the left,\nor click \u201cAdd {self.noun}\u201d "
                  "to begin."),
            font=font(18, slant="italic"), text_color=TEXT_MUTED, justify="center",
        ).pack()
        ornament(inner).pack(fill="x", padx=40, pady=(18, 0))

    # ---- card view -------------------------------------------------------------
    def show_card(self, entity_id):
        ent = self.db.get_entity(entity_id)
        if ent is None:
            self.show_empty()
            return

        self.editing = False
        self.edit_id = None
        self.selected_id = entity_id
        self.clear_main()
        self.highlight_selected()

        bar = self._topbar()
        self.edit_btn = self._button(bar, "Edit", lambda: self.show_edit(entity_id))
        self.edit_btn.pack(side="left")
        self.copy_btn = self._button(
            bar, "Copy", lambda: self.copy_entity(entity_id, self.copy_btn), outline=True)
        self.copy_btn.pack(side="left", padx=(10, 0))
        self._button(bar, "Export", lambda: self.open_export(entity_id),
                     outline=True).pack(side="right")

        body = self._body()
        row = 0

        # Image in a thin gilt frame
        image = self._load_image(ent["image"])
        if image is not None:
            self._image_ref = image  # keep a reference so it isn't garbage collected
            mount = ctk.CTkFrame(body, fg_color=SURFACE_RAISED, border_width=2,
                                 border_color=ACCENT, corner_radius=2)
            mount.grid(row=row, column=0, sticky="w", pady=(2, 20))
            ctk.CTkLabel(mount, text="", image=image).pack(padx=6, pady=6)
            row += 1
        elif ent["image"]:
            ctk.CTkLabel(body, text=f"(image not found: images/{ent['image']})",
                         text_color=TEXT_MUTED, font=font(12, slant="italic")).grid(
                row=row, column=0, sticky="w", pady=(4, 8))
            row += 1

        # Type tag, title, gilt rule
        ctk.CTkLabel(body, text=f"  {ent['type']}  ", font=self.f_small, text_color=TEXT,
                     fg_color=SELECTION_BG, corner_radius=10, height=22).grid(
            row=row, column=0, sticky="w", pady=(0, 8))
        row += 1
        title = ctk.CTkLabel(body, text=ent["name"], font=self.f_title,
                             text_color=TEXT_DISPLAY, anchor="w", justify="left",
                             wraplength=640)
        title.grid(row=row, column=0, sticky="w")
        self.wrap_labels.append((title, 230))
        row += 1
        ornament(body).grid(row=row, column=0, sticky="ew", pady=(10, 2), padx=(0, 18))
        row += 1

        # Details grouped by category (empty fields are hidden)
        values = self.db.get_values(entity_id)
        groups = {}
        for f in self.db.get_fields():
            v = (values.get(f["id"]) or "").strip()
            if v:
                groups.setdefault(f["category"], []).append((f, v))

        if not groups:
            ctk.CTkLabel(body, text="No details yet. Press Edit to add some.",
                         text_color=TEXT_MUTED, font=font(15, slant="italic")).grid(
                row=row, column=0, sticky="w", pady=24)
            return

        for category, items in groups.items():
            section_header(body, category).grid(
                row=row, column=0, sticky="ew", pady=(30, 10), padx=(0, 18))
            row += 1

            for f, v in items:
                shown = v
                if f["field_type"] == "list":
                    shown = "\n".join("\u2022 " + i.strip()
                                      for i in v.splitlines() if i.strip())
                if f["field_type"] == "textarea":
                    lbl = ctk.CTkLabel(body, text=v, font=self.f_body, text_color=TEXT,
                                       anchor="w", justify="left", wraplength=640)
                    lbl.grid(row=row, column=0, sticky="w", pady=4)
                    self.wrap_labels.append((lbl, 230))
                else:
                    line = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
                    line.grid(row=row, column=0, sticky="ew", pady=4)
                    ctk.CTkLabel(line, text=f["name"], font=self.f_label,
                                 text_color=TEXT_LABEL, width=190, anchor="nw",
                                 justify="left").grid(row=0, column=0, sticky="nw")
                    lbl = ctk.CTkLabel(line, text=shown, font=self.f_body, text_color=TEXT,
                                       anchor="w", justify="left", wraplength=470)
                    lbl.grid(row=0, column=1, sticky="w", padx=(10, 0))
                    self.wrap_labels.append((lbl, 430))
                row += 1

    # ---- edit view -------------------------------------------------------------
    def show_edit(self, entity_id=None, preset=None):
        self.editing = True
        self.edit_id = entity_id

        if preset is None:
            if entity_id is not None:
                ent = self.db.get_entity(entity_id)
                preset = {
                    "name": ent["name"], "type": ent["type"], "image": ent["image"] or "",
                    "values": self.db.get_values(entity_id),
                }
            else:
                preset = {"name": "", "type": self.default_entity_type(), "image": "",
                          "values": {}}

        self.clear_main()

        bar = self._topbar()
        self._button(bar, "Save", self.save_edit).pack(side="left")
        self._button(bar, "Cancel", self.cancel_edit, outline=True).pack(side="left", padx=10)
        if entity_id is not None:
            self._button(bar, "Delete", self.delete_current, outline=True,
                         danger=True).pack(side="right")

        body = self._body()
        row = 0

        heading = f"New {self.noun}" if entity_id is None else "Edit"
        ctk.CTkLabel(body, text=heading, font=self.f_header, text_color=TEXT_DISPLAY,
                     anchor="w").grid(row=row, column=0, sticky="w", pady=(2, 4))
        row += 1
        ornament(body).grid(row=row, column=0, sticky="ew", padx=(0, 18), pady=(0, 8))
        row += 1

        # Name
        self._field_label(body, "Name").grid(row=row, column=0, sticky="w", pady=(10, 3))
        row += 1
        self.name_entry = self._entry(body, preset["name"])
        self.name_entry.grid(row=row, column=0, sticky="ew", padx=(0, 18))
        row += 1

        # Type
        self._field_label(body, "Type").grid(row=row, column=0, sticky="w", pady=(12, 3))
        row += 1
        type_options = list(ENTITY_TYPES)
        for extra in (self.default_entity_type(), preset["type"]):
            if extra and extra not in type_options:
                type_options.append(extra)
        self.type_box = styled_combo(body, type_options, width=230)
        self.type_box.set(preset["type"] if preset["type"] else self.default_entity_type())
        self.type_box.grid(row=row, column=0, sticky="w")
        row += 1

        # Image filename
        self._field_label(body, "Image filename (in ./images/)").grid(
            row=row, column=0, sticky="w", pady=(12, 3))
        row += 1
        img_row = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        img_row.grid(row=row, column=0, sticky="ew", padx=(0, 18))
        img_row.grid_columnconfigure(0, weight=1)
        self.image_entry = self._entry(img_row, preset["image"])
        self.image_entry.configure(placeholder_text="hero.png")
        self.image_entry.grid(row=0, column=0, sticky="ew")
        self._button(img_row, "Browse...", self.browse_image, outline=True,
                     width=110).grid(row=0, column=1, padx=(10, 0))
        row += 1

        # Fields by category
        values = preset.get("values", {})
        current_category = None
        for f in self.db.get_fields():
            if f["category"] != current_category:
                current_category = f["category"]
                section_header(body, current_category).grid(
                    row=row, column=0, sticky="ew", padx=(0, 18), pady=(30, 4))
                row += 1

            self._field_label(
                body, f["name"] + ("  (one per line)" if f["field_type"] == "list" else "")
            ).grid(row=row, column=0, sticky="w", pady=(10, 3))
            row += 1

            value = values.get(f["id"], "") or ""
            ftype = f["field_type"]
            if ftype in ("textarea", "list"):
                widget = styled_textbox(body, height=130 if ftype == "textarea" else 96)
                widget.insert("1.0", value)
                self._make_textbox_tabbable(widget)
            else:
                widget = self._entry(body, value)
            widget.grid(row=row, column=0, sticky="ew", padx=(0, 18))
            self.field_widgets[f["id"]] = (widget, ftype)
            row += 1

        self.after(50, self._focus_name)

    def _focus_name(self):
        try:
            self.name_entry.focus_set()
        except (tk.TclError, AttributeError):
            pass

    @staticmethod
    def _make_textbox_tabbable(textbox):
        """Let Tab / Shift+Tab move focus instead of inserting a tab character."""
        def forward(e):
            e.widget.tk_focusNext().focus_set()
            return "break"

        def backward(e):
            e.widget.tk_focusPrev().focus_set()
            return "break"

        textbox.bind("<Tab>", forward)
        for seq in ("<Shift-Tab>", "<ISO_Left_Tab>"):
            try:
                textbox.bind(seq, backward)
            except tk.TclError:
                pass

    def collect_form(self):
        values = {}
        for field_id, (widget, ftype) in self.field_widgets.items():
            raw = widget.get() if ftype == "text" else widget.get("1.0", "end-1c")
            if ftype == "list":
                raw = "\n".join(i.strip() for i in raw.splitlines() if i.strip())
            values[field_id] = raw.strip()
        return {
            "name": self.name_entry.get().strip(),
            "type": self.type_box.get(),
            "image": self.image_entry.get().strip(),
            "values": values,
        }

    def save_edit(self):
        data = self.collect_form()
        if not data["name"]:
            messagebox.showwarning("Name required", "Please give this entry a name.",
                                   parent=self)
            self.name_entry.focus_set()
            return
        entity_id = self.db.save_entity(self.edit_id, data["name"], data["type"],
                                        data["image"], data["values"])
        self.editing = False
        self.selected_id = entity_id
        self.refresh_list()
        self.show_card(entity_id)

    def cancel_edit(self):
        self.editing = False
        target = self.edit_id if self.edit_id is not None else self.selected_id
        if target is not None and self.db.get_entity(target) is not None:
            self.show_card(target)
        else:
            self.show_empty()

    def delete_current(self):
        if self.edit_id is None:
            return
        ent = self.db.get_entity(self.edit_id)
        if ent is None:
            return
        if not messagebox.askyesno(
                "Delete", f"Permanently delete \u201c{ent['name']}\u201d? This can't be undone.",
                parent=self):
            return
        self.db.delete_entity(self.edit_id)
        self.editing = False
        self.edit_id = None
        self.selected_id = None
        self.refresh_list()
        remaining = self.db.search_entities("")
        if remaining:
            self.show_card(remaining[0]["id"])
        else:
            self.show_empty()

    def browse_image(self):
        start = IMAGE_DIR if IMAGE_DIR.exists() else BASE_DIR
        chosen = filedialog.askopenfilename(
            parent=self, title="Choose an image", initialdir=str(start),
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                       ("All files", "*.*")],
        )
        if not chosen:
            return
        src = Path(chosen)
        IMAGE_DIR.mkdir(exist_ok=True)
        dest = IMAGE_DIR / src.name
        try:
            if src.resolve() != dest.resolve():
                # Copy into ./images/, avoiding overwriting a different file
                counter = 1
                while dest.exists():
                    dest = IMAGE_DIR / f"{src.stem}_{counter}{src.suffix}"
                    counter += 1
                shutil.copy2(src, dest)
        except OSError as exc:
            messagebox.showerror("Couldn't copy image", str(exc), parent=self)
            return
        self.image_entry.delete(0, "end")
        self.image_entry.insert(0, dest.name)

    # ---- copy ------------------------------------------------------------------
    def copy_entity(self, entity_id, button=None):
        """Copy the entity's non-empty fields to the clipboard as plain text."""
        text = build_plain_text(self.db, entity_id)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()  # keep the clipboard contents available
        if button is not None:
            button.configure(text="Copied \u2713")
            self.after(1500, lambda: self._reset_button_text(button, "Copy"))

    @staticmethod
    def _reset_button_text(button, text):
        try:
            button.configure(text=text)
        except tk.TclError:
            pass  # card was rebuilt in the meantime

    # ---- export ------------------------------------------------------------------
    def open_export(self, entity_id):
        ent = self.db.get_entity(entity_id)
        if ent is None:
            return
        ExportWindow(self, ent["name"], build_plain_text(self.db, entity_id))


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    App().mainloop()