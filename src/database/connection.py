"""SQLite connection manager, schema, and profile switching.

A *profile* is simply one SQLite file (for example ``Characters.sqlite`` or
``Worldbuilding.sqlite``). This module is the only place in the application that
opens database files, creates or upgrades the schema, or switches between
profiles. Everything above it (services, UI) receives a ``DatabaseConnection``
and never deals with file paths or pragmas directly.

Layout of this file
-------------------
1. Constants and exceptions
2. Schema: creation, upgrade of older files, starter templates
3. Profile files: validation and naming
4. Startup profile: which file to open at launch
5. DatabaseConnection: the connection manager used by the rest of the app
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Union

from src.database import seeds

PathLike = Union[str, Path]

# =========================================================================== #
# 1. Constants and exceptions
# =========================================================================== #
SCHEMA_VERSION = 1   # stored in the file via PRAGMA user_version

DEFAULT_PROFILE_NAME = "Character.sqlite"
LEGACY_PROFILE_NAME = "database.sqlite"          # used by the first version of the app
LAST_PROFILE_FILE_NAME = "last_profile.txt"      # remembers the last profile loaded

_SQLITE_HEADER = b"SQLite format 3\x00"
_REQUIRED_TABLES = frozenset({"entities", "fields", "field_values"})


class ProfileError(Exception):
    """A file can't be used as a profile. The message is safe to show to the user."""


class NoActiveProfileError(RuntimeError):
    """The connection was used before a profile was opened (or after it was closed)."""


# =========================================================================== #
# 2. Schema
# =========================================================================== #
_FIELD_TYPES_SQL = ", ".join(f"'{t}'" for t in seeds.FIELD_TYPES)

_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS entities (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    type  TEXT NOT NULL DEFAULT '{seeds.ENTITY_TYPE_CHARACTER}',
    image TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fields (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    category   TEXT NOT NULL COLLATE NOCASE,
    name       TEXT NOT NULL COLLATE NOCASE,
    multiline  INTEGER NOT NULL DEFAULT 0,   -- deprecated: kept so version 1 of the app can still read the file
    field_type TEXT NOT NULL DEFAULT '{seeds.DEFAULT_FIELD_TYPE}'
               CHECK (field_type IN ({_FIELD_TYPES_SQL})),
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


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Create any missing tables, upgrade older files in place, and stamp the version.

    Safe to call on every open: it only adds what is missing and never removes data.
    Raises ProfileError if the file was written by a newer version of the app.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ProfileError(
            "That profile was created by a newer version of Character Builder "
            "and can't be opened safely.")
    conn.executescript(_SCHEMA_SQL)
    _upgrade_older_files(conn)
    sync_categories(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def _upgrade_older_files(conn: sqlite3.Connection) -> None:
    """Bring files made by earlier versions of the app up to the current layout."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(fields)")}
    if "field_type" not in columns:
        conn.execute(
            "ALTER TABLE fields ADD COLUMN field_type TEXT NOT NULL "
            f"DEFAULT '{seeds.DEFAULT_FIELD_TYPE}' CHECK (field_type IN ({_FIELD_TYPES_SQL}))")
        if "multiline" in columns:
            conn.execute(
                "UPDATE fields SET field_type = ? WHERE multiline = 1",
                (seeds.FIELD_TYPE_TEXTAREA,))


def sync_categories(conn: sqlite3.Connection) -> None:
    """Make sure every category a field uses also exists in the categories table.

    New categories are appended after existing ones, ordered by the position of
    their first field. This is how files from before the categories table existed
    keep their original category order.
    """
    known = {row[0].lower() for row in conn.execute("SELECT name FROM categories")}
    top = conn.execute("SELECT MAX(sort_order) FROM categories").fetchone()[0]
    next_order = 0 if top is None else top + 1
    used = conn.execute(
        "SELECT category, MIN(sort_order) AS first_position FROM fields "
        "GROUP BY category ORDER BY first_position").fetchall()
    with conn:
        for category, _first in used:
            if category.lower() not in known:
                conn.execute("INSERT INTO categories (name, sort_order) VALUES (?, ?)",
                             (category, next_order))
                known.add(category.lower())
                next_order += 1


def is_blank(conn: sqlite3.Connection) -> bool:
    """True for a brand-new profile: no entries, no fields and no categories."""
    total = conn.execute(
        "SELECT (SELECT COUNT(*) FROM entities) + (SELECT COUNT(*) FROM fields) "
        "+ (SELECT COUNT(*) FROM categories)").fetchone()[0]
    return total == 0


def seed_if_blank(conn: sqlite3.Connection, template: seeds.Template) -> bool:
    """Fill a brand-new profile with a template's categories and fields.

    Returns True if seeding happened. A profile that already holds entries, fields or
    categories is never seeded, so fields the user deliberately deleted don't come back.
    """
    if not is_blank(conn):
        return False
    position = 0
    with conn:
        for order, category in enumerate(template["categories"]):
            conn.execute("INSERT INTO categories (name, sort_order) VALUES (?, ?)",
                         (category["name"], order))
            for field in category["fields"]:
                conn.execute(
                    "INSERT INTO fields (category, name, multiline, field_type, sort_order) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (category["name"], field["name"],
                     int(field["type"] == seeds.FIELD_TYPE_TEXTAREA),
                     field["type"], position))
                position += 1
    return True


# =========================================================================== #
# 3. Profile files: validation and naming
# =========================================================================== #
def validate_profile_file(path: PathLike) -> None:
    """Check that an existing file can be opened as a profile.

    Returns normally if it can. Raises ProfileError, with a message fit to show the
    user, if it can't. The file is only ever read (never modified) by this check.
    An empty (zero-byte) file is accepted: it is set up when the profile is opened.
    """
    path = Path(path)
    if not path.exists():
        raise ProfileError("That file doesn't exist.")
    if not path.is_file():
        raise ProfileError("That is a folder, not a database file.")
    try:
        size = path.stat().st_size
        with open(path, "rb") as handle:
            header = handle.read(16)
    except OSError as exc:
        raise ProfileError(f"Couldn't read that file: {exc}") from exc
    if size == 0:
        return
    if header != _SQLITE_HEADER:
        raise ProfileError("That isn't a SQLite database file.")

    try:
        probe = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            version = probe.execute("PRAGMA user_version").fetchone()[0]
            tables = {row[0] for row in probe.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            probe.close()
    except sqlite3.Error as exc:
        raise ProfileError(f"Couldn't open that database: {exc}") from exc

    tables = {name for name in tables if not name.startswith("sqlite_")}
    if tables and not _REQUIRED_TABLES <= tables:
        raise ProfileError(
            "That database wasn't made by Character Builder, so it hasn't been "
            "opened or changed.")
    if version > SCHEMA_VERSION:
        raise ProfileError(
            "That profile was created by a newer version of Character Builder "
            "and can't be opened safely.")


_GENERIC_PROFILE_NAMES = frozenset(
    {"database", "db", "data", "profile", "app", "new", "untitled", "default"})


def profile_noun(path: PathLike) -> str:
    """The singular word for one entry in a profile, taken from its file name.

    ``characters.sqlite`` -> "Character", ``places.sqlite`` -> "Place",
    ``factions.sqlite`` -> "Faction", ``database.sqlite`` -> "Entry".
    The UI uses it for the Add button ("Add Character") and for new-entry headings.
    """
    stem = Path(path).stem
    lowered = stem.lower()
    if "character" in lowered:
        return seeds.ENTITY_TYPE_CHARACTER
    if any(word in lowered for word in ("place", "location", "world")):
        return seeds.ENTITY_TYPE_PLACE

    words = [word for word in re.split(r"[\s_\-.]+", stem) if word]
    if not words or lowered in _GENERIC_PROFILE_NAMES:
        return "Entry"

    last = words[-1].lower()
    if last.endswith("ies") and len(last) > 3:
        last = last[:-3] + "y"
    elif last.endswith(("ches", "shes", "sses", "xes", "zes")):
        last = last[:-2]
    elif last.endswith("s") and not last.endswith("ss") and len(last) > 1:
        last = last[:-1]
    return " ".join([word.capitalize() for word in words[:-1]] + [last.capitalize()])


# =========================================================================== #
# 4. Startup profile
# =========================================================================== #
def _is_usable(path: Path) -> bool:
    try:
        validate_profile_file(path)
    except ProfileError:
        return False
    return True


def recall_profile(settings_file: PathLike) -> Optional[Path]:
    """The profile saved by remember_profile, if that file still exists and is usable."""
    try:
        text = Path(settings_file).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_file() and _is_usable(candidate):
        return candidate.resolve()
    return None


def remember_profile(settings_file: PathLike, profile: PathLike) -> bool:
    """Save which profile was loaded last. Returns False if it couldn't be saved."""
    try:
        Path(settings_file).write_text(str(profile), encoding="utf-8")
    except OSError:
        return False
    return True


def resolve_startup_profile(base_dir: PathLike) -> Path:
    """Decide which profile file to open at launch (the file may not exist yet).

    Order of preference:
      1. the profile loaded last time, if it still exists and is usable
      2. ``Character.sqlite`` in ``base_dir``
      3. ``database.sqlite`` (the first version's file), but only while
         ``Character.sqlite`` doesn't exist, so upgrading never hides saved entries
      4. otherwise ``Character.sqlite``, which will be created
    """
    base = Path(base_dir)
    last = recall_profile(base / LAST_PROFILE_FILE_NAME)
    if last is not None:
        return last
    default = base / DEFAULT_PROFILE_NAME
    legacy = base / LEGACY_PROFILE_NAME
    if not default.exists() and legacy.is_file() and _is_usable(legacy):
        return legacy.resolve()
    return default.resolve()


# =========================================================================== #
# 5. DatabaseConnection
# =========================================================================== #
def _connect(path: Path) -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")   # needed for ON DELETE CASCADE
    except sqlite3.Error as exc:
        raise ProfileError(f"Couldn't open that database: {exc}") from exc
    return conn


class DatabaseConnection:
    """Owns the one active SQLite connection and switches it between profiles.

    Typical use::

        db = DatabaseConnection()
        db.open(path, create=True, template=seeds.CHARACTER_TEMPLATE)
        rows = db.connection.execute("SELECT * FROM entities").fetchall()
        with db.transaction() as conn:
            conn.execute("INSERT INTO entities (name) VALUES (?)", ("Aria",))
        db.switch_profile(other_path)        # File > Load Profile
        db.close()

    Switching is safe: the new file is opened and checked first, and the current
    profile is only closed once the new one is ready. If anything goes wrong the
    current profile stays active and untouched.
    """

    def __init__(self) -> None:
        self._conn: Optional[sqlite3.Connection] = None
        self._path: Optional[Path] = None

    # ---- state -------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._conn is not None

    @property
    def path(self) -> Optional[Path]:
        """Full path of the active profile, or None if nothing is open."""
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        """The active sqlite3 connection (rows behave like dicts)."""
        if self._conn is None:
            raise NoActiveProfileError("No profile is open.")
        return self._conn

    # ---- opening, switching, closing ------------------------------------------
    def open(self, path: PathLike, *, create: bool = False,
             template: Optional[seeds.Template] = None) -> Path:
        """Open a profile, replacing the active one only if this succeeds.

        create    allow creating the file if it doesn't exist yet
        template  starter categories and fields for a brand-new, empty profile
                  (ignored for profiles that already contain data)
        Raises ProfileError if the file can't be used. Returns the resolved path.
        """
        path = Path(path).expanduser().resolve()
        if path.exists():
            validate_profile_file(path)
        elif not create:
            raise ProfileError("That file doesn't exist.")
        elif not path.parent.is_dir():
            raise ProfileError(f"The folder {path.parent} doesn't exist.")

        conn = _connect(path)
        try:
            initialize_schema(conn)
            if template is not None:
                seed_if_blank(conn, template)
        except ProfileError:
            conn.close()
            raise
        except sqlite3.Error as exc:
            conn.close()
            raise ProfileError(f"Couldn't set up that database: {exc}") from exc

        previous = self._conn
        self._conn, self._path = conn, path
        if previous is not None:
            previous.close()
        return path

    def switch_profile(self, path: PathLike, *,
                       template: Optional[seeds.Template] = None) -> bool:
        """File > Load Profile: make another existing file the active profile.

        Returns True if the profile changed and False if that file was already
        active. Raises ProfileError (leaving the current profile active) if the
        file doesn't exist or isn't a usable profile.
        """
        target = Path(path).expanduser().resolve()
        if self.is_open and target == self._path:
            return False
        self.open(target, create=False, template=template)
        return True

    def close(self) -> None:
        """Close the active profile. Safe to call more than once."""
        if self._conn is not None:
            self._conn.close()
        self._conn = None
        self._path = None

    def __enter__(self) -> "DatabaseConnection":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # ---- transactions ---------------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Group statements so they all succeed or none do.

        Commits when the block finishes and rolls everything back if it raises.
        Calls can be nested: an inner block simply joins the outer transaction.
        """
        conn = self.connection
        if conn.in_transaction:
            yield conn
            return
        conn.execute("BEGIN")
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        else:
            conn.commit()
