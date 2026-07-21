import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Icon } from './Icon'
import { api } from '../lib/api/client'
import { faFloppyDisk, faPlus, faTrash, faXmark } from '../lib/icons'

/** AIOps Secrets Manager — Hearth-backed keys or Bitwarden BSM config. */
export function SecretsManagerPanel() {
  const qc = useQueryClient()
  const secrets = useQuery({
    queryKey: ['aiops-secrets'],
    queryFn: () => api.aiopsSecretsStatus(),
  })

  const [backend, setBackend] = useState<'hearth' | 'bitwarden'>('hearth')
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [bwProject, setBwProject] = useState('')
  const [bwServer, setBwServer] = useState('')
  const [bwToken, setBwToken] = useState('')
  const [bwOverride, setBwOverride] = useState(true)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const data = secrets.data
    if (!data) return
    setBackend((data.backend as 'hearth' | 'bitwarden') || 'hearth')
    setBwProject(data.bitwarden?.project_id || '')
    setBwServer(data.bitwarden?.server_url || '')
    setBwOverride(data.bitwarden?.override_existing !== false)
  }, [secrets.data])

  const saveManager = useMutation({
    mutationFn: () =>
      api.aiopsSecretsManagerSave({
        backend,
        access_token: backend === 'bitwarden' && bwToken.trim() ? bwToken.trim() : undefined,
        bitwarden: {
          enabled: backend === 'bitwarden',
          project_id: bwProject,
          server_url: bwServer,
          override_existing: bwOverride,
        },
      }),
    onSuccess: () => {
      setBwToken('')
      setMessage(
        backend === 'hearth'
          ? 'Hearth secrets backend saved. Restart the agent sidecar if this is the first enable.'
          : 'Bitwarden BSM settings saved. Restart the agent sidecar to pull secrets.',
      )
      void qc.invalidateQueries({ queryKey: ['aiops-secrets'] })
    },
    onError: (err) => setMessage((err as Error).message),
  })

  const upsert = useMutation({
    mutationFn: () => api.aiopsSecretsUpsert(newKey.trim(), newValue),
    onSuccess: () => {
      setNewKey('')
      setNewValue('')
      setMessage('Secret saved.')
      void qc.invalidateQueries({ queryKey: ['aiops-secrets'] })
    },
    onError: (err) => setMessage((err as Error).message),
  })

  const remove = useMutation({
    mutationFn: (key: string) => api.aiopsSecretsDelete(key),
    onSuccess: () => {
      setMessage('Secret deleted.')
      void qc.invalidateQueries({ queryKey: ['aiops-secrets'] })
    },
    onError: (err) => setMessage((err as Error).message),
  })

  const data = secrets.data
  const writable = data?.hearth?.agent_home_writable
  const pluginOk = data?.hearth?.plugin_installed

  return (
    <section className="wizard-step">
      <h3>
        <span className="wizard-num">5</span> Secrets Manager
      </h3>
      <p className="muted" style={{ marginTop: 0 }}>
        Provide tool/API keys Hermes can use (for example <code>JELLYFIN_API_TOKEN</code>). Keys are
        stored by Hearth and injected into Hermes via a SecretSource plugin — not by growing the
        Deployment env. Vaultwarden is <strong>not</strong> compatible with Hermes Bitwarden BSM.
      </p>

      {secrets.isError ? (
        <div className="error-banner">{(secrets.error as Error).message}</div>
      ) : null}
      {message ? (
        <div className="panel flash" style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
          <span>{message}</span>
          <button className="icon-btn" type="button" title="Dismiss" onClick={() => setMessage(null)}>
            <Icon icon={faXmark} label="Dismiss" />
          </button>
        </div>
      ) : null}

      {!data?.hearth?.agent_home ? (
        <div className="error-banner">
          <code>HEARTH_AGENT_HOME</code> is not set. Mount the agent-data PVC on the hearth container
          so secrets and the Hermes plugin can be synced.
        </div>
      ) : null}
      {data?.hearth?.agent_home && !writable ? (
        <div className="error-banner">Agent home is not writable by Hearth ({data.hearth.agent_home}).</div>
      ) : null}

      <div className="grid">
        <div className="field">
          <label htmlFor="secrets-backend">Backend</label>
          <select
            id="secrets-backend"
            value={backend}
            onChange={(e) => setBackend(e.target.value as 'hearth' | 'bitwarden')}
          >
            <option value="hearth">Hearth (recommended)</option>
            <option value="bitwarden">Bitwarden Secrets Manager</option>
          </select>
        </div>
      </div>

      {backend === 'hearth' ? (
        <>
          <div className="muted" style={{ marginBottom: 8 }}>
            Plugin {pluginOk ? 'installed' : 'not installed yet'} · {data?.hearth?.key_count ?? 0}{' '}
            key(s)
            {data?.hearth?.restart_hint ? (
              <>
                <br />
                {data.hearth.restart_hint}
              </>
            ) : null}
          </div>
          <div className="secrets-keys">
            {(data?.keys || []).map((row) => (
              <div key={row.key} className="secrets-key-row">
                <code>{row.key}</code>
                <span className="muted">{row.has_value ? '••••••••' : '(empty)'}</span>
                <button
                  className="icon-btn"
                  type="button"
                  title={`Delete ${row.key}`}
                  aria-label={`Delete ${row.key}`}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(row.key)}
                >
                  <Icon icon={faTrash} label="Delete" />
                </button>
              </div>
            ))}
            {!data?.keys?.length ? <div className="muted">No secrets yet.</div> : null}
          </div>
          <div className="grid" style={{ marginTop: 10 }}>
            <div className="field">
              <label htmlFor="secret-key">Key</label>
              <input
                id="secret-key"
                value={newKey}
                placeholder="JELLYFIN_API_TOKEN"
                onChange={(e) => setNewKey(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="field">
              <label htmlFor="secret-value">Value</label>
              <input
                id="secret-value"
                type="password"
                value={newValue}
                placeholder="secret value"
                onChange={(e) => setNewValue(e.target.value)}
                autoComplete="new-password"
              />
            </div>
          </div>
          <div className="actions" style={{ marginTop: 8 }}>
            <button
              className="icon-btn"
              type="button"
              title="Add / update secret"
              disabled={!newKey.trim() || upsert.isPending}
              onClick={() => upsert.mutate()}
            >
              <Icon icon={faPlus} label="Add secret" spin={upsert.isPending} />
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="error-banner" style={{ marginBottom: 8 }}>
            Use Bitwarden <strong>Secrets Manager</strong> (machine account + <code>bws</code>), not
            Vaultwarden / password vault.
          </div>
          <div className="grid">
            <div className="field">
              <label htmlFor="bw-project">Project ID</label>
              <input
                id="bw-project"
                value={bwProject}
                onChange={(e) => setBwProject(e.target.value)}
                placeholder="uuid"
                autoComplete="off"
              />
            </div>
            <div className="field">
              <label htmlFor="bw-server">Server URL (optional)</label>
              <input
                id="bw-server"
                value={bwServer}
                onChange={(e) => setBwServer(e.target.value)}
                placeholder="https://vault.bitwarden.eu or self-hosted SM"
                autoComplete="off"
              />
            </div>
            <div className="field">
              <label htmlFor="bw-token">
                Access token {data?.bitwarden?.has_token ? '(saved — leave blank to keep)' : ''}
              </label>
              <input
                id="bw-token"
                type="password"
                value={bwToken}
                onChange={(e) => setBwToken(e.target.value)}
                placeholder="0...."
                autoComplete="new-password"
              />
            </div>
            <label className="bool-toggle">
              <input
                type="checkbox"
                checked={bwOverride}
                onChange={(e) => setBwOverride(e.target.checked)}
              />
              Override existing env values from Bitwarden
            </label>
          </div>
        </>
      )}

      <div className="actions" style={{ marginTop: 12 }}>
        <button
          className="icon-btn primary"
          type="button"
          title="Save Secrets Manager"
          disabled={saveManager.isPending}
          onClick={() => saveManager.mutate()}
        >
          <Icon icon={faFloppyDisk} label="Save Secrets Manager" spin={saveManager.isPending} />
        </button>
      </div>
    </section>
  )
}
