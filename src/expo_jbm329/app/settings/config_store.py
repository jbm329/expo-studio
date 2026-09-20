"""Configuration store for Expo.

This module provides thread-safe access to configuration files, including
settings, logging configuration, and database connections. It handles
atomic read/write operations, deep merging of defaults, and validation.

Attributes:
    DEFAULT_SETTINGS (dict): Default application settings.
    DEFAULT_LOG_CONFIG (dict): Default logging configuration.
"""

from __future__ import annotations

import copy
import json
from threading import RLock
from typing import TYPE_CHECKING, Literal

from expo_jbm329.app.settings.json_types import JsonObject, int_value, object_from_mapping, object_or_empty
from expo_jbm329.i18n.language import Language
from expo_jbm329.utils.path_manager import (
    get_connections_config_path,
    get_log_config_path,
    get_rest_connections_config_path,
    get_settings_path,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

DEFAULT_WORKBENCH_SETTINGS: JsonObject = {
    "language": "en",  # ISO 639-1
    "theme": "system",
    "highlighter_theme": "system",
    "gen_top_n": 1000,
    "undo_limit_per_tab": 20,
    "max_size_allow_undo_mb": 100,
}

DEFAULT_CSV_SETTINGS: JsonObject = {
    "read_chunk_size_rows": 100000,
    "write_chunk_size_rows": 100000,
    "default_encoding": "utf-8",
    "sniff_delimiter": True,
    "default_sep": ",",
}

DEFAULT_EXCEL_SETTINGS: JsonObject = {
    "chunk_size_rows": 25000,
    "max_rows_per_sheet": 1048576,
    "streaming": True,
}

DEFAULT_SCHEMA_CACHE_SETTINGS: JsonObject = {
    "ttl_seconds": 300,
    "prefetch_limit": 600,  # 0 => No limit
    "prefetch_batch_size": 100,  # objects/batch
}

DEFAULT_SETTINGS: JsonObject = {
    "workbench": {
        **DEFAULT_WORKBENCH_SETTINGS,
    },
    "documents_dir": None,  # None => use default
    "csv": {
        **DEFAULT_CSV_SETTINGS,
    },
    "excel": {
        **DEFAULT_EXCEL_SETTINGS,
    },
    "schema_cache": {
        **DEFAULT_SCHEMA_CACHE_SETTINGS,
    },
}

# Threading safety
_lock = RLock()

# Local cache for settings.json only
_settings_cache: JsonObject | None = None


# =====================================================================
#  Atomic Write Helper
# =====================================================================
def _atomic_write_json(path: Path, data: Mapping[str, object]) -> None:
    """Writes a dictionary to a JSON file atomically.

    Args:
        path: Path to the target JSON file.
        data: Dictionary to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# =====================================================================
#  Deep Merge
# =====================================================================
def merge_defaults(defaults: Mapping[str, object], user: Mapping[str, object]) -> JsonObject:
    """Deep-merges default values into a user configuration dictionary.

    Args:
        defaults: The dictionary containing default values.
        user: The dictionary containing user overrides.

    Returns:
        A new dictionary with merged values.
    """
    out: JsonObject = copy.deepcopy(dict(defaults))
    for key, user_val in user.items():
        if key not in defaults:
            out[key] = user_val
        else:
            def_val = defaults[key]
            if isinstance(def_val, dict) and isinstance(user_val, dict):
                out[key] = merge_defaults(object_from_mapping(def_val), object_from_mapping(user_val))
            else:
                out[key] = user_val
    return out


def _require_json_object(value: object) -> JsonObject:
    """Return value as a JSON object or raise for malformed config data."""
    if not isinstance(value, dict):
        msg = "Expected a JSON object."
        raise TypeError(msg)
    return object_from_mapping(value)


# =====================================================================
#  SETTINGS.JSON
# =====================================================================
def load_settings() -> JsonObject:
    """Loads settings.json with merging, caching, and validation.

    If the settings file does not exist or is corrupt, it is initialized with
    defaults.

    Returns:
        A copy of the current settings dictionary.
    """
    global _settings_cache  # noqa: PLW0603 - module-level settings cache is guarded by _lock.

    with _lock:
        if _settings_cache is not None:
            return _settings_cache.copy()

        p = get_settings_path()

        # File missing → create with defaults
        if not p.exists():
            merged = copy.deepcopy(DEFAULT_SETTINGS)
            _atomic_write_json(p, merged)
            _settings_cache = merged
            return merged.copy()

        # Try to load existing file
        try:
            loaded: object = json.loads(p.read_text(encoding="utf-8"))
            user = _require_json_object(loaded)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            # Corrupt → reset
            merged = copy.deepcopy(DEFAULT_SETTINGS)
            _atomic_write_json(p, merged)
            _settings_cache = merged
            return merged.copy()

        # Deep merge defaults → user config
        merged = merge_defaults(DEFAULT_SETTINGS, user)

        # Validate (in-place fix)
        _validate_settings_inplace(merged)

        _settings_cache = merged
        return merged.copy()


def save_settings(settings: JsonObject) -> None:
    """Validates and persists settings to disk and updates the cache.

    Args:
        settings: The settings dictionary to save.
    """
    global _settings_cache  # noqa: PLW0603 - module-level settings cache is guarded by _lock.
    with _lock:
        _validate_settings_inplace(settings)
        _atomic_write_json(get_settings_path(), settings)
        _settings_cache = settings.copy()


def _validate_settings_inplace(s: JsonObject) -> None:
    """Normalizes and validates settings in-place.

    Ensures that required blocks exist, types are correct, and values are
    within sensible ranges based on DEFAULT_SETTINGS.

    Args:
        s: The settings dictionary to validate.
    """

    # --- Helpers ---------------------------------------------------------------
    def _coerce_int(
        val: object,
        default: object,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        """Coerces a value to an integer with optional clamping.

        Args:
            val: The value to coerce.
            default: The fallback value if coercion fails.
            min_value: Optional minimum bound.
            max_value: Optional maximum bound.

        Returns:
            The coerced integer.
        """
        default_int = int_value(default)
        iv = int_value(val, default_int)
        if min_value is not None and iv < min_value:
            iv = min_value
        if max_value is not None and iv > max_value:
            iv = max_value
        return iv

    def _coerce_bool(val: object, default: object) -> bool:
        """Coerces a value to a boolean.

        Args:
            val: The value to coerce.
            default: The fallback value if coercion is ambiguous.

        Returns:
            The coerced boolean.
        """
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "y")
        if isinstance(val, (int, float)):
            return bool(val)
        return bool(default)

    def _coerce_str(val: object, default: object) -> str:
        """Coerces a value to a non-empty string.

        Args:
            val: The value to coerce.
            default: The fallback value if the string is empty or invalid.

        Returns:
            The coerced string.
        """
        if isinstance(val, str):
            v = val.strip()
            return v or str(default)
        return str(default)

    def _ensure_dict(root: JsonObject, key: str, default_dict: Mapping[str, object]) -> JsonObject:
        """Ensures a key exists in a dictionary and is itself a dictionary.

        Args:
            root: The parent dictionary.
            key: The key to check.
            default_dict: The default dictionary to use if missing/invalid.

        Returns:
            The dictionary at root[key].
        """
        sub = root.get(key)
        if not isinstance(sub, dict):
            root[key] = copy.deepcopy(default_dict)
            return object_or_empty(root[key])

        normalized = object_from_mapping(sub)
        root[key] = normalized
        return normalized

    # --- Ensure presence of main nested blocks ---------------------------------
    ed = _ensure_dict(s, "workbench", DEFAULT_WORKBENCH_SETTINGS)
    csv_block = _ensure_dict(s, "csv", DEFAULT_CSV_SETTINGS)
    excel_block = _ensure_dict(s, "excel", DEFAULT_EXCEL_SETTINGS)
    sc = _ensure_dict(s, "schema_cache", DEFAULT_SCHEMA_CACHE_SETTINGS)

    # --- documents_dir: allow None or a non-empty string -----------------------
    docdir = s.get("documents_dir", DEFAULT_SETTINGS.get("documents_dir"))
    if docdir is None:
        s["documents_dir"] = None
    elif isinstance(docdir, str):
        docdir = docdir.strip()
        s["documents_dir"] = docdir or None
    else:
        s["documents_dir"] = None

    # --- workbench ----------------------------------------------------------------
    # Language:  ISO 639-1 language code
    lang = str(ed.get("language", DEFAULT_WORKBENCH_SETTINGS["language"])).strip().lower()
    if lang not in {_lang.value for _lang in Language}:
        lang = str(DEFAULT_WORKBENCH_SETTINGS["language"])
    ed["language"] = lang

    # Theme: accept "light", "dark" or "system"
    theme = str(ed.get("theme", DEFAULT_WORKBENCH_SETTINGS["theme"])).strip().lower()
    if theme not in ("light", "dark", "system"):
        theme = str(DEFAULT_WORKBENCH_SETTINGS["theme"])
    ed["theme"] = theme

    ed["gen_top_n"] = _coerce_int(
        ed.get("gen_top_n", DEFAULT_WORKBENCH_SETTINGS["gen_top_n"]),
        DEFAULT_WORKBENCH_SETTINGS["gen_top_n"],
        min_value=0,  # allow 0 to indicate "no limit"
    )
    ed["undo_limit_per_tab"] = _coerce_int(
        ed.get("undo_limit_per_tab", DEFAULT_WORKBENCH_SETTINGS["undo_limit_per_tab"]),
        DEFAULT_WORKBENCH_SETTINGS["undo_limit_per_tab"],
        min_value=1,
    )
    ed["max_size_allow_undo_mb"] = _coerce_int(
        ed.get("max_size_allow_undo_mb", DEFAULT_WORKBENCH_SETTINGS["max_size_allow_undo_mb"]),
        DEFAULT_WORKBENCH_SETTINGS["max_size_allow_undo_mb"],
        min_value=1,
    )

    # --- csv -------------------------------------------------------------------
    csv_block["read_chunk_size_rows"] = _coerce_int(
        csv_block.get("read_chunk_size_rows", DEFAULT_CSV_SETTINGS["read_chunk_size_rows"]),
        DEFAULT_CSV_SETTINGS["read_chunk_size_rows"],
        min_value=1,
    )
    csv_block["write_chunk_size_rows"] = _coerce_int(
        csv_block.get("write_chunk_size_rows", DEFAULT_CSV_SETTINGS["write_chunk_size_rows"]),
        DEFAULT_CSV_SETTINGS["write_chunk_size_rows"],
        min_value=1,
    )
    csv_block["default_encoding"] = _coerce_str(
        csv_block.get("default_encoding", DEFAULT_CSV_SETTINGS["default_encoding"]),
        DEFAULT_CSV_SETTINGS["default_encoding"],
    ).lower()
    csv_block["sniff_delimiter"] = _coerce_bool(
        csv_block.get("sniff_delimiter", DEFAULT_CSV_SETTINGS["sniff_delimiter"]),
        DEFAULT_CSV_SETTINGS["sniff_delimiter"],
    )
    csv_block["default_sep"] = _coerce_str(
        csv_block.get("default_sep", DEFAULT_CSV_SETTINGS["default_sep"]), DEFAULT_CSV_SETTINGS["default_sep"]
    )

    # --- excel -----------------------------------------------------------------
    excel_block["chunk_size_rows"] = _coerce_int(
        excel_block.get("chunk_size_rows", DEFAULT_EXCEL_SETTINGS["chunk_size_rows"]),
        DEFAULT_EXCEL_SETTINGS["chunk_size_rows"],
        min_value=1,
    )
    # Clamp to Excel's row limit per sheet (1,048,576)
    excel_block["max_rows_per_sheet"] = _coerce_int(
        excel_block.get("max_rows_per_sheet", DEFAULT_EXCEL_SETTINGS["max_rows_per_sheet"]),
        DEFAULT_EXCEL_SETTINGS["max_rows_per_sheet"],
        min_value=1,
        max_value=int_value(DEFAULT_EXCEL_SETTINGS["max_rows_per_sheet"], 1_048_576),
    )
    excel_block["streaming"] = _coerce_bool(
        excel_block.get("streaming", DEFAULT_EXCEL_SETTINGS["streaming"]), DEFAULT_EXCEL_SETTINGS["streaming"]
    )
    # --- schema_cache ----------------------------------------------------------
    sc["ttl_seconds"] = _coerce_int(
        sc.get("ttl_seconds", DEFAULT_SCHEMA_CACHE_SETTINGS["ttl_seconds"]),
        DEFAULT_SCHEMA_CACHE_SETTINGS["ttl_seconds"],
        min_value=1,
    )
    sc["prefetch_limit"] = _coerce_int(
        sc.get("prefetch_limit", DEFAULT_SCHEMA_CACHE_SETTINGS["prefetch_limit"]),
        DEFAULT_SCHEMA_CACHE_SETTINGS["prefetch_limit"],
        min_value=0,  # 0 => no limit
    )
    sc["prefetch_batch_size"] = _coerce_int(
        sc.get("prefetch_batch_size", DEFAULT_SCHEMA_CACHE_SETTINGS["prefetch_batch_size"]),
        DEFAULT_SCHEMA_CACHE_SETTINGS["prefetch_batch_size"],
        min_value=1,
    )


# =====================================================================
#  CONNECTIONS.JSON
# =====================================================================
ConnectionConfig = JsonObject
ConnectionsConfig = dict[str, ConnectionConfig]
RestConnectionConfig = JsonObject
RestConnectionsConfig = dict[str, RestConnectionConfig]
LogConfig = JsonObject


def read_connections() -> ConnectionsConfig:
    """Loads and normalizes connections.json.

    Returns:
        A dictionary mapping connection names to their configurations.
    """
    with _lock:
        p = get_connections_config_path()

        def normalize_entry(conn: Mapping[str, object]) -> ConnectionConfig:
            """Normalizes individual connection entries.

            Args:
                conn: The connection configuration dictionary.

            Returns:
                A normalized copy of the connection dictionary.
            """
            c: ConnectionConfig = dict(conn)

            # trusted_connection normalization
            tc = str(c.get("trusted_connection", "")).strip().lower()
            if tc in ("1", "true", "yes", "y"):
                c["trusted_connection"] = "yes"
            else:
                c["trusted_connection"] = "no"

            # port normalization
            if "port" in c:
                port = c["port"]
                if isinstance(port, str | bytes | bytearray | int | float):
                    try:
                        c["port"] = int(port)
                    except ValueError:
                        c.pop("port", None)
                else:
                    c.pop("port", None)

            return c

        if not p.exists():
            _atomic_write_json(p, {})
            return {}

        try:
            raw = p.read_text("utf-8").strip()
            if not raw:
                _atomic_write_json(p, {})
                return {}

            loaded: object = json.loads(raw)
            data = _require_json_object(loaded)
            out: ConnectionsConfig = {}
            for name, conn in data.items():
                if isinstance(name, str) and isinstance(conn, dict):
                    out[name] = normalize_entry(object_from_mapping(conn))

            _atomic_write_json(p, out)

        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            _atomic_write_json(p, {})
            return {}
        else:
            return out


def write_connections(conns: ConnectionsConfig) -> None:
    """Atomically writes the entire connections configuration to disk.

    Args:
        conns: A dictionary mapping connection names to configurations.
    """
    with _lock:
        out = {name: dict(cfg) for name, cfg in conns.items() if isinstance(name, str) and isinstance(cfg, dict)}
        _atomic_write_json(get_connections_config_path(), out)


# =====================================================================
#  REST_CONNECTIONS.JSON
# =====================================================================
def read_rest_connections() -> RestConnectionsConfig:
    """Loads and normalizes rest_connections.json."""
    with _lock:
        p = get_rest_connections_config_path()

        if not p.exists():
            _atomic_write_json(p, {})
            return {}

        try:
            raw = p.read_text("utf-8").strip()
            if not raw:
                _atomic_write_json(p, {})
                return {}

            loaded: object = json.loads(raw)
            data = _require_json_object(loaded)
            out: RestConnectionsConfig = {}
            for name, cfg in data.items():
                if isinstance(name, str) and isinstance(cfg, dict):
                    out[name] = _normalize_rest_entry(object_from_mapping(cfg))

            _atomic_write_json(p, out)

        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            _atomic_write_json(p, {})
            return {}
        else:
            return out


def write_rest_connections(conns: RestConnectionsConfig) -> None:
    """Atomically writes rest_connections.json."""
    with _lock:
        out = {name: dict(cfg) for name, cfg in conns.items() if isinstance(name, str) and isinstance(cfg, dict)}
        _atomic_write_json(get_rest_connections_config_path(), out)


def _normalize_rest_entry(cfg: Mapping[str, object]) -> RestConnectionConfig:
    """Normalizes a single REST connection entry."""
    c: RestConnectionConfig = dict(cfg)

    c["url"] = str(c.get("url", "")).strip()
    c["response_path"] = str(c.get("response_path", "")).strip() or None
    c["method"] = _normalize_rest_method(c.get("method"))

    # headers / params
    for key in ("headers", "query_params"):
        v = c.get(key)
        if not isinstance(v, dict):
            c[key] = {}
        else:
            c[key] = {str(k): str(vv) for k, vv in v.items()}

    # auth
    auth = c.get("auth")
    if not isinstance(auth, dict):
        c["auth"] = {"type": "none"}
    else:
        auth_data = object_from_mapping(auth)
        at = str(auth_data.get("type", "none")).lower()
        if at not in ("none", "bearer", "basic", "api_key", "oauth2"):
            at = "none"
        auth_cfg: JsonObject = {"type": at}
        c["auth"] = auth_cfg
        if at == "bearer":
            token = auth_data.get("token")
            if isinstance(token, str) and token:
                auth_cfg["token"] = token
        elif at == "basic":
            username = auth_data.get("username")
            password = auth_data.get("password")
            if isinstance(username, str) and username:
                auth_cfg["username"] = username
            if isinstance(password, str) and password:
                auth_cfg["password"] = password
        elif at == "api_key":
            api_key_name = auth_data.get("api_key_name")
            api_key_value = auth_data.get("api_key_value")
            api_key_location = str(auth_data.get("api_key_location", "")).lower()
            if isinstance(api_key_name, str) and api_key_name:
                auth_cfg["api_key_name"] = api_key_name
            if isinstance(api_key_value, str) and api_key_value:
                auth_cfg["api_key_value"] = api_key_value
            if api_key_location in ("header", "query"):
                auth_cfg["api_key_location"] = api_key_location
        elif at == "oauth2":
            token_url = auth_data.get("token_url")
            client_id = auth_data.get("client_id")
            client_secret = auth_data.get("client_secret")
            scope = auth_data.get("scope")
            refresh_token = auth_data.get("refresh_token")
            access_token = auth_data.get("access_token")
            grant_type = str(auth_data.get("grant_type", "client_credentials")).lower()
            if grant_type not in ("client_credentials", "refresh_token"):
                grant_type = "client_credentials"
            auth_cfg["grant_type"] = grant_type
            if isinstance(token_url, str) and token_url:
                auth_cfg["token_url"] = token_url
            if isinstance(client_id, str) and client_id:
                auth_cfg["client_id"] = client_id
            if isinstance(client_secret, str) and client_secret:
                auth_cfg["client_secret"] = client_secret
            if isinstance(scope, str) and scope:
                auth_cfg["scope"] = scope
            if isinstance(refresh_token, str) and refresh_token:
                auth_cfg["refresh_token"] = refresh_token
            if isinstance(access_token, str) and access_token:
                auth_cfg["access_token"] = access_token

    pagination = c.get("pagination")
    if not isinstance(pagination, dict):
        c["pagination"] = {"type": "none"}
    else:
        pagination_data = object_from_mapping(pagination)
        pagination_type = str(pagination_data.get("type", "none")).lower()
        if pagination_type != "page_number":
            c["pagination"] = {"type": "none"}
        else:
            normalized_pagination: JsonObject = {
                "type": "page_number",
                "page_param": str(pagination_data.get("page_param", "")).strip(),
                "start_page": _normalize_positive_int(pagination_data.get("start_page"), default=1),
            }
            page_size_param = str(pagination_data.get("page_size_param", "")).strip()
            if page_size_param:
                normalized_pagination["page_size_param"] = page_size_param

            page_size = _normalize_optional_positive_int(pagination_data.get("page_size"))
            if page_size is not None:
                normalized_pagination["page_size"] = page_size

            max_pages = _normalize_optional_positive_int(pagination_data.get("max_pages"))
            if max_pages is not None:
                normalized_pagination["max_pages"] = max_pages

            c["pagination"] = normalized_pagination

    return c


def _normalize_rest_method(value: object) -> Literal["GET", "POST"]:
    """Normalize REST method to a supported uppercase value."""
    if isinstance(value, str):
        method = value.strip().upper()
        if method == "POST":
            return "POST"
        if method == "GET":
            return "GET"
    return "GET"


def _normalize_positive_int(value: object, *, default: int) -> int:
    """Normalize a positive integer value with a fallback."""
    normalized = int_value(value, default)
    return normalized if normalized >= 1 else default


def _normalize_optional_positive_int(value: object) -> int | None:
    """Normalize an optional positive integer value."""
    if value in (None, ""):
        return None
    normalized = int_value(value, 0)
    return normalized if normalized >= 1 else None


# =====================================================================
#  LOGCONFIG.JSON
# =====================================================================

DEFAULT_LOG_FILE_HANDLER_CONFIG: JsonObject = {
    "level": "INFO",
    "formatter": "verbose",
    "maxBytes": 5_000_000,
    "backupCount": 3,
}

DEFAULT_LOG_STDOUT_HANDLER_CONFIG: JsonObject = {
    "level": "WARNING",
    "formatter": "default",
}

DEFAULT_LOGGER_CONFIG: JsonObject = {"level": "INFO", "propagate": True}

DEFAULT_LOG_CONFIG: LogConfig = {
    "logger_level": "INFO",
    "handlers": {
        "file": {**DEFAULT_LOG_FILE_HANDLER_CONFIG},
        "stdout": {**DEFAULT_LOG_STDOUT_HANDLER_CONFIG},
    },
    "loggers": {
        "applogger.ui": {"level": "INFO", "propagate": True},
        "applogger.service": {"level": "WARNING", "propagate": True},
        "applogger.jobs": {"level": "INFO", "propagate": True},
        "applogger.db": {"level": "WARNING", "propagate": True},
    },
    "third_party_log_level": "WARNING",
}


def read_log_config() -> LogConfig:
    """Loads, merges, and normalizes the logging configuration.

    Returns:
        The merged logging configuration dictionary.
    """
    with _lock:
        p = get_log_config_path()

        # Missing → create default
        if not p.exists():
            _atomic_write_json(p, DEFAULT_LOG_CONFIG)
            return copy.deepcopy(DEFAULT_LOG_CONFIG)

        try:
            loaded: object = json.loads(p.read_text("utf-8"))
            data = _require_json_object(loaded)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            _atomic_write_json(p, DEFAULT_LOG_CONFIG)
            return copy.deepcopy(DEFAULT_LOG_CONFIG)

        merged = merge_defaults(DEFAULT_LOG_CONFIG, data)
        _validate_log_config_inplace(merged)
        return merged


def write_log_config(cfg: LogConfig) -> None:
    """Persists the logging configuration to disk.

    Args:
        cfg: The logging configuration dictionary to save.
    """
    with _lock:
        _validate_log_config_inplace(cfg)
        _atomic_write_json(get_log_config_path(), cfg)


def _validate_log_config_inplace(cfg: LogConfig) -> None:
    """Ensures that logging handler and logger definitions are sane.

    Args:
        cfg: The logging configuration dictionary to validate in-place.
    """
    handlers_value = cfg.get("handlers", {})
    if not isinstance(handlers_value, dict):
        cfg["handlers"] = {}
        return
    handlers = object_from_mapping(handlers_value)

    valid_handlers = {"file", "stdout"}

    # Remove anything not supported
    for name in list(handlers.keys()):
        if name not in valid_handlers:
            handlers.pop(name, None)
            continue

        handler = handlers[name]
        if not isinstance(handler, dict):
            handlers.pop(name, None)
            continue
        handler = object_from_mapping(handler)
        handlers[name] = handler

        # Required keys
        handler.setdefault("level", "INFO")
        handler.setdefault("formatter", "default")

        if name == "file":
            handler.setdefault("maxBytes", 5_000_000)
            handler.setdefault("backupCount", 3)

    cfg["handlers"] = handlers

    loggers_value = cfg.get("loggers", {})
    if not isinstance(loggers_value, dict):
        cfg["loggers"] = {}
        return
    loggers = object_from_mapping(loggers_value)

    for lname, spec_value in list(loggers.items()):
        if not isinstance(lname, str) or not isinstance(spec_value, dict):
            loggers.pop(lname, None)
            continue
        spec = object_from_mapping(spec_value)
        loggers[lname] = spec

        # level normalization
        lvl = spec.get("level", "INFO")
        if isinstance(lvl, str):
            lvl_up = lvl.strip().upper()
            if lvl_up not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}:
                spec["level"] = "INFO"
            else:
                spec["level"] = lvl_up
        elif isinstance(lvl, int):
            spec["level"] = lvl
        else:
            spec["level"] = "INFO"

        # propagate normalisering: vår modell vill ha True (root bär handlers)
        spec["propagate"] = bool(spec.get("propagate", True))

    cfg["loggers"] = loggers

    # -------- third_party_log_level(single wildcard setting) ---------

    lvl = cfg.get("third_party_log_level", "WARNING")
    if isinstance(lvl, str):
        lvl_up = lvl.strip().upper()
        if lvl_up not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}:
            cfg["third_party_log_level"] = "WARNING"
        else:
            cfg["third_party_log_level"] = lvl_up
    elif isinstance(lvl, int):
        cfg["third_party_log_level"] = lvl
    else:
        cfg["third_party_log_level"] = "WARNING"
