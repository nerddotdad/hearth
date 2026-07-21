"""Hearth-managed secrets for Hermes Agent (store, export, plugin sync, config patch)."""

from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


PROTECTED_KEYS = frozenset(
    {
        "API_SERVER_KEY",
        "API_SERVER_ENABLED",
        "API_SERVER_HOST",
        "API_SERVER_PORT",
        "API_SERVER_CORS_ORIGINS",
        "HEARTH_AGENT_API_KEY",
        "HEARTH_SANDBOX_AGENT_API_KEY",
        "HEARTH_SECRETS_TOKEN",
        "BWS_ACCESS_TOKEN",
        "TRIAGE_AUTH_TOKEN",
        "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD",
        "HERMES_DASHBOARD_BASIC_AUTH_SECRET",
        "ADMIN_PASS",
    }
)

DEFAULT_PASSTHROUGH = [
    "JELLYFIN_API_TOKEN",
    "JELLYFIN_API_URL",
    "JELLYFIN_PUBLIC_URL",
    "HOMELAB_DOCS_BASE_URL",
    "HOMELAB_GRAFANA_URL",
    "SEARXNG_URL",
    "HEARTH_SANDBOX_AGENT_API_KEY",
    "HEARTH_MCP_URL",
    "HEARTH_SECRETS_TOKEN",
]

PLUGIN_NAME = "hearth-secrets"
_LOCK = threading.Lock()


class SecretsError(RuntimeError):
    pass


def incidents_dir() -> Path:
    return Path(os.environ.get("INCIDENT_DIR", "/data/incidents"))


def secrets_path() -> Path:
    return incidents_dir() / ".hearth-agent-secrets.json"


def manager_path() -> Path:
    return incidents_dir() / ".hearth-secrets-manager.json"


def agent_home() -> Path | None:
    raw = (os.environ.get("HEARTH_AGENT_HOME") or "").strip()
    if not raw:
        return None
    return Path(raw)


def plugin_source_dir() -> Path:
    env = (os.environ.get("HEARTH_HERMES_PLUGIN_DIR") or "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "hermes_plugin" / PLUGIN_NAME


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_secrets() -> dict[str, str]:
    raw = _read_json(secrets_path(), {})
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        k = str(key).strip()
        if not k or k.startswith("#"):
            continue
        out[k] = "" if value is None else str(value)
    return out


def load_manager() -> dict[str, Any]:
    raw = _read_json(manager_path(), {})
    if not isinstance(raw, dict):
        raw = {}
    backend = str(raw.get("backend") or "hearth").strip().lower()
    if backend not in ("hearth", "bitwarden"):
        backend = "hearth"
    bitwarden = raw.get("bitwarden") if isinstance(raw.get("bitwarden"), dict) else {}
    return {
        "backend": backend,
        "bitwarden": {
            "enabled": bool(bitwarden.get("enabled", backend == "bitwarden")),
            "project_id": str(bitwarden.get("project_id") or ""),
            "server_url": str(bitwarden.get("server_url") or ""),
            "override_existing": bool(bitwarden.get("override_existing", True)),
            "access_token_env": str(bitwarden.get("access_token_env") or "BWS_ACCESS_TOKEN"),
            "has_token": bool(bitwarden.get("has_token")),
        },
    }


def list_secret_keys() -> list[dict[str, Any]]:
    secrets = load_secrets()
    return [
        {"key": key, "masked": True, "has_value": bool(str(secrets[key]).strip())}
        for key in sorted(secrets)
    ]


def upsert_secret(key: str, value: str) -> None:
    key = str(key or "").strip()
    if not key:
        raise SecretsError("key is required")
    if not _valid_env_key(key):
        raise SecretsError("key must look like an environment variable name (A-Z, 0-9, _)")
    if key in PROTECTED_KEYS or key.startswith("API_SERVER_"):
        raise SecretsError(f"key {key} is protected and managed by Hearth/platform bootstrap")
    with _LOCK:
        secrets = load_secrets()
        secrets[key] = str(value)
        _write_json(secrets_path(), secrets)
        _ensure_passthrough_keys(list(secrets.keys()))


def delete_secret(key: str) -> None:
    key = str(key or "").strip()
    if not key:
        raise SecretsError("key is required")
    if key in PROTECTED_KEYS or key.startswith("API_SERVER_"):
        raise SecretsError(f"key {key} is protected")
    with _LOCK:
        secrets = load_secrets()
        if key not in secrets:
            raise SecretsError("secret not found")
        del secrets[key]
        _write_json(secrets_path(), secrets)


def export_secrets() -> dict[str, str]:
    """Full map for the Hermes SecretSource plugin (loopback only)."""
    return load_secrets()


def save_manager(
    *,
    backend: str,
    bitwarden: dict[str, Any] | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    backend = str(backend or "hearth").strip().lower()
    if backend not in ("hearth", "bitwarden"):
        raise SecretsError("backend must be hearth or bitwarden")
    current = load_manager()
    bw = dict(current.get("bitwarden") or {})
    if bitwarden:
        if "project_id" in bitwarden:
            bw["project_id"] = str(bitwarden.get("project_id") or "")
        if "server_url" in bitwarden:
            bw["server_url"] = str(bitwarden.get("server_url") or "")
        if "override_existing" in bitwarden:
            bw["override_existing"] = bool(bitwarden.get("override_existing"))
        if "enabled" in bitwarden:
            bw["enabled"] = bool(bitwarden.get("enabled"))
        if "access_token_env" in bitwarden:
            bw["access_token_env"] = str(bitwarden.get("access_token_env") or "BWS_ACCESS_TOKEN")
    bw["enabled"] = backend == "bitwarden" and bool(bw.get("enabled", True))
    if access_token is not None and str(access_token).strip():
        _set_dotenv_key(str(bw.get("access_token_env") or "BWS_ACCESS_TOKEN"), str(access_token).strip())
        bw["has_token"] = True
    payload = {"backend": backend, "bitwarden": bw}
    with _LOCK:
        _write_json(manager_path(), payload)
        sync_plugin_and_config(backend=backend, bitwarden=bw)
    return status()


def status() -> dict[str, Any]:
    mgr = load_manager()
    home = agent_home()
    plugin_dst = (home / "plugins" / PLUGIN_NAME) if home else None
    plugin_installed = bool(plugin_dst and (plugin_dst / "plugin.yaml").is_file())
    return {
        "backend": mgr["backend"],
        "bitwarden": {
            "enabled": mgr["bitwarden"]["enabled"],
            "project_id": mgr["bitwarden"]["project_id"],
            "server_url": mgr["bitwarden"]["server_url"],
            "override_existing": mgr["bitwarden"]["override_existing"],
            "access_token_env": mgr["bitwarden"]["access_token_env"],
            "has_token": bool(mgr["bitwarden"].get("has_token")),
        },
        "hearth": {
            "key_count": len(load_secrets()),
            "plugin_installed": plugin_installed,
            "agent_home": str(home) if home else None,
            "agent_home_writable": bool(home and home.exists() and os.access(home, os.W_OK)),
            "restart_hint": (
                "Restart the agent sidecar after enabling Hearth secrets or changing many keys "
                "so Hermes child processes reload the SecretSource plugin."
            ),
        },
        "keys": list_secret_keys(),
    }


def sync_plugin_and_config(
    *,
    backend: str | None = None,
    bitwarden: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy bundled plugin into agent home and patch secrets: in config.yaml."""
    mgr = load_manager()
    backend = (backend or mgr["backend"]).strip().lower()
    bitwarden = bitwarden or mgr.get("bitwarden") or {}
    home = agent_home()
    result: dict[str, Any] = {"ok": True, "plugin_synced": False, "config_patched": False}
    if home is None:
        result["ok"] = False
        result["error"] = "HEARTH_AGENT_HOME is not set (mount agent-data on the hearth container)"
        return result
    home.mkdir(parents=True, exist_ok=True)

    if backend == "hearth":
        src = plugin_source_dir()
        if not (src / "plugin.yaml").is_file():
            result["ok"] = False
            result["error"] = f"bundled plugin missing at {src}"
            return result
        dst = home / "plugins" / PLUGIN_NAME
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("plugin.yaml", "__init__.py"):
            shutil.copy2(src / name, dst / name)
        result["plugin_synced"] = True
        _patch_config_yaml(
            home / "config.yaml",
            backend="hearth",
            bitwarden=bitwarden,
            passthrough_keys=list(load_secrets().keys()),
        )
        result["config_patched"] = True
    else:
        _patch_config_yaml(
            home / "config.yaml",
            backend="bitwarden",
            bitwarden=bitwarden,
            passthrough_keys=list(load_secrets().keys()),
        )
        result["config_patched"] = True
    return result


def ensure_on_startup() -> dict[str, Any]:
    """Best-effort sync when hearth boots (non-fatal)."""
    try:
        ensure_bootstrap_token_in_agent_env()
        return sync_plugin_and_config()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _valid_env_key(key: str) -> bool:
    if not key or key[0].isdigit():
        return False
    return all(c.isalnum() or c == "_" for c in key)


def _ensure_passthrough_keys(keys: list[str]) -> None:
    home = agent_home()
    if home is None:
        return
    cfg_path = home / "config.yaml"
    if not cfg_path.is_file() or yaml is None:
        return
    try:
        with cfg_path.open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception:
        return
    if not isinstance(cfg, dict):
        return
    terminal = cfg.setdefault("terminal", {})
    if not isinstance(terminal, dict):
        terminal = {}
        cfg["terminal"] = terminal
    existing = terminal.get("env_passthrough") or []
    if not isinstance(existing, list):
        existing = []
    merged = list(dict.fromkeys([*[str(x) for x in existing], *DEFAULT_PASSTHROUGH, *keys]))
    terminal["env_passthrough"] = merged
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, default_flow_style=False, sort_keys=False)


def _patch_config_yaml(
    cfg_path: Path,
    *,
    backend: str,
    bitwarden: dict[str, Any],
    passthrough_keys: list[str],
) -> None:
    if yaml is None:
        raise SecretsError("PyYAML is required to patch Hermes config.yaml")
    cfg: dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            with cfg_path.open(encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            if isinstance(loaded, dict):
                cfg = loaded
        except Exception:
            cfg = {}
    secrets = cfg.setdefault("secrets", {})
    if not isinstance(secrets, dict):
        secrets = {}
        cfg["secrets"] = secrets

    if backend == "hearth":
        # Do not put "hearth" in secrets.sources — Hermes validates that list
        # before plugins load and warns "unknown source". Enabled SecretSource
        # plugins still run after registration (and our plugin re-applies then).
        secrets.pop("sources", None)
        secrets["hearth"] = {
            "enabled": True,
            "override_existing": True,
            "export_url": os.environ.get(
                "HEARTH_SECRETS_EXPORT_URL", "http://127.0.0.1:8000/api/aiops/secrets/export"
            ),
            "token_env": "HEARTH_SECRETS_TOKEN",
        }
        # Keep bitwarden disabled when hearth is selected.
        bw = secrets.get("bitwarden") if isinstance(secrets.get("bitwarden"), dict) else {}
        bw["enabled"] = False
        secrets["bitwarden"] = bw
    else:
        secrets["sources"] = ["bitwarden"]
        secrets["bitwarden"] = {
            "enabled": True,
            "project_id": str(bitwarden.get("project_id") or ""),
            "server_url": str(bitwarden.get("server_url") or ""),
            "override_existing": bool(bitwarden.get("override_existing", True)),
            "access_token_env": str(bitwarden.get("access_token_env") or "BWS_ACCESS_TOKEN"),
            "auto_install": True,
        }
        hearth = secrets.get("hearth") if isinstance(secrets.get("hearth"), dict) else {}
        hearth["enabled"] = False
        secrets["hearth"] = hearth

    terminal = cfg.setdefault("terminal", {})
    if not isinstance(terminal, dict):
        terminal = {}
        cfg["terminal"] = terminal
    existing = terminal.get("env_passthrough") or []
    if not isinstance(existing, list):
        existing = []
    terminal["env_passthrough"] = list(
        dict.fromkeys([*[str(x) for x in existing], *DEFAULT_PASSTHROUGH, *passthrough_keys])
    )

    # Hermes discovers plugins but leaves them "not enabled" until listed here.
    # https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins
    plugins = cfg.setdefault("plugins", {})
    if not isinstance(plugins, dict):
        plugins = {}
        cfg["plugins"] = plugins
    enabled = plugins.get("enabled") or []
    if not isinstance(enabled, list):
        enabled = []
    enabled_names = [str(x) for x in enabled]
    if backend == "hearth":
        if PLUGIN_NAME not in enabled_names:
            enabled_names.append(PLUGIN_NAME)
    plugins["enabled"] = enabled_names
    # Never leave hearth-secrets on the deny list.
    disabled = plugins.get("disabled") or []
    if isinstance(disabled, list) and PLUGIN_NAME in disabled:
        plugins["disabled"] = [str(x) for x in disabled if str(x) != PLUGIN_NAME]

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, default_flow_style=False, sort_keys=False)


def _set_dotenv_key(key: str, value: str) -> None:
    home = agent_home()
    if home is None:
        raise SecretsError("HEARTH_AGENT_HOME is not set")
    env_path = home / ".env"
    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}="
    filtered = [ln for ln in lines if not ln.startswith(prefix)]
    filtered.append(f"{key}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(filtered) + "\n", encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass


def bootstrap_token() -> str:
    """Token the plugin uses to call export — prefer dedicated, else sandbox key."""
    return (
        (os.environ.get("HEARTH_SECRETS_TOKEN") or "").strip()
        or (os.environ.get("HEARTH_SANDBOX_AGENT_API_KEY") or "").strip()
        or (os.environ.get("HEARTH_AGENT_API_KEY") or "").strip()
    )


def ensure_bootstrap_token_in_agent_env() -> None:
    """Write HEARTH_SECRETS_TOKEN into agent .env so the plugin can authenticate."""
    token = bootstrap_token()
    if not token or agent_home() is None:
        return
    try:
        _set_dotenv_key("HEARTH_SECRETS_TOKEN", token)
    except SecretsError:
        pass
