# Hearth

> **Product name:** Hearth — homelab incident desk (alerts in, tickets out, agents optional).  
> **Image repo:** still `ghcr.io/nerddotdad/homelab-alert-bridge` (rename cutover is a follow-up).  
> The [truecharts](https://github.com/nerddotdad/truecharts) repo only pins the GHCR tag in Deployment manifests; edit sources here.

## Flow

```text
Alertmanager → alerts inbox (UI: /alerts)
                    ↓ auto-raise rules (Settings) OR manual "Raise incident"
              incident record
                    ↓ notification settings
                  ntfy
```

1. **`POST /hook`** — ingest alerts into the **inbox** (Prometheus integration)
2. **Auto-raise** — configurable rules create incidents automatically (default: `critical` only)
3. **Alerts inbox** — review, multi-select, **Raise incident**
4. **Incidents UI** — ack, merge, enrich, resolve; notifications flow **incident → ntfy**
5. **Manual incidents** — `+ New incident` without any alert
6. **Hermes** — optional AI investigation from the incident page

## Integrations (modular)

Settings → Integrations configures:

| Integration | Kind | Role |
|-------------|------|------|
| **Prometheus** | ingest | Alertmanager / Grafana webhooks → `/hook` |
| **ntfy** | notify | Incident push notifications |
| **Hermes** | investigate | WebUI agent sessions |

New adapters implement the protocol in `integrations/` and register in `integrations/registry.py`.

## Configuration (Grafana-style)

Every setting can come from an **environment variable** or the **Settings UI**.

| Source | Behavior |
|--------|----------|
| Env var set (non-empty) | Applied and **locked** in the UI (`env` badge) |
| Env unset / empty | Editable in Settings; persisted on the PVC (`hearth_settings.json`) |

Legacy `notification_settings.json` and `auto_raise_settings.json` are migrated on first startup.

Common env keys: `NTFY_*`, `HERMES_*`, `INCIDENTS_PUBLIC_BASE_URL`, `PROMETHEUS_ENABLED`, `NTFY_ENABLED`, `HERMES_ENABLED`, `IGNORED_ALERTNAMES`, `TRIAGE_AUTH_TOKEN`, `INCIDENTS_AUTH_TOKEN`.

## URLs

| Surface | Path |
|---------|------|
| **Incidents** | `https://incidents.${DOMAIN_0}/` |
| **Alerts inbox** | `https://incidents.${DOMAIN_0}/alerts` |
| **Settings** | `https://incidents.${DOMAIN_0}/settings` |

## Lazy lists + JQL search

Incident and alert lists load **25 rows at a time** with **infinite scroll**. Search uses a small JQL-style language.

| Surface | Examples |
|---------|----------|
| **Incidents** | `status:open severity>=warning title~"flux"` |
| **Alerts inbox** | `status:firing alertname:Homelab* namespace:flux-system` |

**List APIs:** `GET /api/list/incidents`, `GET /api/list/alerts` — params: `offset`, `limit`, `status`, `q`.  
**Settings API:** `GET/POST /api/settings`, `POST /api/settings/test/<id>`.

## Agent investigations (Hermes)

```text
Investigate → Hermes session/new + chat/start
           → Agent panel (SSE proxy + session poll)
Open in Hermes → https://hermes.<domain>/?session_id=<id>
```

Built by **Build Image** (`.github/workflows/build-image.yml`) on push to `main` or manual **workflow_dispatch**.

**`VERSION`** → GHCR tag; **Renovate** updates the truecharts Deployment pin.
