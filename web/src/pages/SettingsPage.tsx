import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Icon } from '../components/Icon'
import { api, type SettingsField } from '../lib/api/client'
import { faArrowsRotate, faFloppyDisk, faWifi } from '../lib/icons'

const AIOPS_AGENTS = [{ id: 'hermes', label: 'Hermes' }] as const
const MODEL_PLATFORMS = [{ id: 'ollama', label: 'Ollama' }] as const

type Tab = 'general' | 'integrations' | 'aiops' | 'auto-raise' | 'display'

const TABS: { id: Tab; label: string }[] = [
  { id: 'general', label: 'General' },
  { id: 'integrations', label: 'Integrations' },
  { id: 'aiops', label: 'AIOps' },
  { id: 'auto-raise', label: 'Auto-raise' },
  { id: 'display', label: 'Display' },
]

function fieldMap(fields: SettingsField[] | undefined): Record<string, SettingsField> {
  const out: Record<string, SettingsField> = {}
  for (const f of fields || []) out[f.key] = f
  return out
}

function FieldInput({
  field,
  value,
  onChange,
}: {
  field?: SettingsField
  value: string
  onChange: (v: string) => void
}) {
  if (!field) return null
  const locked = Boolean(field.locked)
  return (
    <div className={`field ${locked ? 'field-locked' : ''}`}>
      <label>
        {field.label || field.key}
        {locked ? <span className="lock-badge">env</span> : null}
      </label>
      {field.hint ? <div className="muted">{field.hint}</div> : null}
      <input
        type={field.secret && !locked ? 'password' : 'text'}
        value={locked ? String(field.value ?? '') : value}
        disabled={locked}
        placeholder={field.secret && !locked ? 'leave blank to keep' : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

function BoolToggle({
  field,
  checked,
  onChange,
}: {
  field?: SettingsField
  checked: boolean
  onChange: (v: boolean) => void
}) {
  if (!field) return null
  const locked = Boolean(field.locked)
  return (
    <label className="actions" style={{ justifyContent: 'flex-start' }}>
      <input
        type="checkbox"
        checked={checked}
        disabled={locked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <strong>
          {field.label || field.key}
          {locked ? <span className="lock-badge">env</span> : null}
        </strong>
        {field.hint ? (
          <>
            <br />
            <span className="muted">{field.hint}</span>
          </>
        ) : null}
      </span>
    </label>
  )
}

function SelectField({
  field,
  value,
  options,
  onChange,
  disabled,
}: {
  field?: SettingsField
  value: string
  options: Array<{ id: string; label: string }>
  onChange: (v: string) => void
  disabled?: boolean
}) {
  if (!field) return null
  const locked = Boolean(field.locked)
  const known = options.some((o) => o.id === value)
  return (
    <div className={`field ${locked ? 'field-locked' : ''}`}>
      <label>
        {field.label || field.key}
        {locked ? <span className="lock-badge">env</span> : null}
      </label>
      {field.hint ? <div className="muted">{field.hint}</div> : null}
      <select
        value={value}
        disabled={locked || disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {!known && value ? <option value={value}>{value}</option> : null}
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  )
}

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>(() => {
    const hash = window.location.hash.replace(/^#/, '') as Tab
    return TABS.some((t) => t.id === hash) ? hash : 'general'
  })
  const [draft, setDraft] = useState<Record<string, string | boolean>>({})
  const [flash, setFlash] = useState('')
  const qc = useQueryClient()

  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.getSettings(),
  })
  const aiops = useQuery({
    queryKey: ['aiops-status'],
    queryFn: () => api.aiopsStatus(),
  })

  const groups = settings.data?.groups || {}
  const core = fieldMap(groups.core)
  const prometheus = fieldMap(groups.prometheus)
  const ntfy = fieldMap(groups.ntfy)
  const hermes = fieldMap(groups.hermes)
  const autoRaise = fieldMap(groups.auto_raise)
  const display = fieldMap(groups.display)

  const val = (key: string, field?: SettingsField) => {
    if (key in draft) return draft[key]
    if (!field) return ''
    if (typeof field.raw_value === 'boolean') return field.raw_value
    if (typeof field.value === 'boolean') return field.value
    return String(field.value ?? '')
  }

  const agentKind = String(val('hermes.agent', hermes['hermes.agent']) || 'hermes')
  const modelPlatform = String(
    val('hermes.model_platform', hermes['hermes.model_platform']) || 'ollama',
  )
  const ollamaUrl = String(val('hermes.ollama_url', hermes['hermes.ollama_url']) || '')
  const selectedModel = String(val('hermes.agent_model', hermes['hermes.agent_model']) || '')

  const ollamaModels = useQuery({
    queryKey: ['aiops-models', modelPlatform, ollamaUrl],
    queryFn: () => api.aiopsModels(modelPlatform, ollamaUrl || undefined),
    enabled: tab === 'aiops' && modelPlatform === 'ollama' && Boolean(ollamaUrl.trim()),
    retry: 1,
  })

  const modelOptions = useMemo(() => {
    const fromApi = (ollamaModels.data?.models || []).map((m) => ({ id: m, label: m }))
    if (selectedModel && !fromApi.some((m) => m.id === selectedModel)) {
      return [{ id: selectedModel, label: selectedModel }, ...fromApi]
    }
    return fromApi
  }, [ollamaModels.data?.models, selectedModel])

  const save = useMutation({
    mutationFn: (updates: Record<string, unknown>) => api.saveSettings(updates),
    onSuccess: (res) => {
      setFlash(`Saved ${res.changed.length || 0} field(s)`)
      setDraft({})
      void qc.invalidateQueries({ queryKey: ['settings'] })
      void qc.invalidateQueries({ queryKey: ['aiops-status'] })
    },
  })

  const test = useMutation({
    mutationFn: (id: string) => api.testIntegration(id),
    onSuccess: (res) => setFlash(res.ok ? `OK: ${res.message}` : `Failed: ${res.message}`),
    onError: (err) => setFlash((err as Error).message),
  })

  const saveKeys = (keys: string[], fields?: Record<string, SettingsField>) => {
    const updates: Record<string, unknown> = {}
    for (const key of keys) {
      if (key in draft) {
        updates[key] = draft[key]
        continue
      }
      // Wizard-style saves: persist current displayed values, not only dirty draft keys.
      if (fields?.[key] && !fields[key].locked) {
        updates[key] = val(key, fields[key])
      }
    }
    if (!Object.keys(updates).length) {
      setFlash('No changes to save')
      return
    }
    save.mutate(updates)
  }

  const integPills = useMemo(() => {
    return (settings.data?.integrations || []).map((row) => {
      const name = row.id === 'hermes' ? 'AIOps' : row.name || row.id
      if (!row.enabled) return `${name}: off`
      return `${name}: ${row.id}`
    })
  }, [settings.data])

  function selectTab(next: Tab) {
    setTab(next)
    history.replaceState(null, '', `#${next}`)
  }

  if (settings.isLoading) return <div className="panel muted">Loading settings…</div>
  if (settings.isError) {
    return <div className="panel error-banner">{(settings.error as Error).message}</div>
  }

  return (
    <>
      {flash ? <div className="panel flash">{flash}</div> : null}
      <div className="actions" style={{ marginBottom: 12 }}>
        {integPills.map((p) => (
          <span key={p} className="badge">
            {p}
          </span>
        ))}
      </div>
      <p className="muted">
        Fields marked <span className="lock-badge">env</span> are set by environment variables and
        cannot be edited here.
      </p>

      <div className="settings-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            className={tab === t.id ? 'active' : undefined}
            aria-selected={tab === t.id}
            onClick={() => selectTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'general' ? (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>General</h2>
          <div className="grid">
            {(
              [
                'core.incidents_public_base_url',
                'core.grafana_public_url',
                'core.default_runbook_url',
                'core.incidents_auth_token',
                'core.triage_auth_token',
              ] as const
            ).map((key) => (
              <FieldInput
                key={key}
                field={core[key]}
                value={String(val(key, core[key]))}
                onChange={(v) => setDraft((d) => ({ ...d, [key]: v }))}
              />
            ))}
            <div className="actions">
              <button
                className="icon-btn primary"
                type="button"
                title="Save general"
                aria-label="Save general"
                onClick={() =>
                  saveKeys([
                    'core.incidents_public_base_url',
                    'core.grafana_public_url',
                    'core.default_runbook_url',
                    'core.incidents_auth_token',
                    'core.triage_auth_token',
                  ])
                }
              >
                <Icon icon={faFloppyDisk} label="Save general" />
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {tab === 'integrations' ? (
        <>
          <div className="panel">
            <h2 style={{ marginTop: 0 }}>Prometheus</h2>
            <div className="grid">
              <BoolToggle
                field={prometheus['prometheus.enabled']}
                checked={Boolean(val('prometheus.enabled', prometheus['prometheus.enabled']))}
                onChange={(v) => setDraft((d) => ({ ...d, 'prometheus.enabled': v }))}
              />
              <FieldInput
                field={prometheus['prometheus.ignored_alertnames']}
                value={String(val('prometheus.ignored_alertnames', prometheus['prometheus.ignored_alertnames']))}
                onChange={(v) => setDraft((d) => ({ ...d, 'prometheus.ignored_alertnames': v }))}
              />
              <div className="actions">
                <button
                  className="icon-btn primary"
                  type="button"
                  title="Save Prometheus"
                  aria-label="Save Prometheus"
                  onClick={() =>
                    saveKeys(['prometheus.enabled', 'prometheus.ignored_alertnames'])
                  }
                >
                  <Icon icon={faFloppyDisk} label="Save Prometheus" />
                </button>
                <button
                  className="icon-btn"
                  type="button"
                  title="Test Prometheus"
                  aria-label="Test Prometheus"
                  onClick={() => test.mutate('prometheus')}
                >
                  <Icon icon={faWifi} label="Test Prometheus" />
                </button>
              </div>
            </div>
          </div>
          <div className="panel">
            <h2 style={{ marginTop: 0 }}>ntfy</h2>
            <div className="grid">
              <BoolToggle
                field={ntfy['ntfy.enabled']}
                checked={Boolean(val('ntfy.enabled', ntfy['ntfy.enabled']))}
                onChange={(v) => setDraft((d) => ({ ...d, 'ntfy.enabled': v }))}
              />
              {(['ntfy.base_url', 'ntfy.topic', 'ntfy.public_url'] as const).map((key) => (
                <FieldInput
                  key={key}
                  field={ntfy[key]}
                  value={String(val(key, ntfy[key]))}
                  onChange={(v) => setDraft((d) => ({ ...d, [key]: v }))}
                />
              ))}
              <div className="actions">
                <button
                  className="icon-btn primary"
                  type="button"
                  title="Save ntfy"
                  aria-label="Save ntfy"
                  onClick={() =>
                    saveKeys(['ntfy.enabled', 'ntfy.base_url', 'ntfy.topic', 'ntfy.public_url'])
                  }
                >
                  <Icon icon={faFloppyDisk} label="Save ntfy" />
                </button>
                <button
                  className="icon-btn"
                  type="button"
                  title="Test ntfy"
                  aria-label="Test ntfy"
                  onClick={() => test.mutate('ntfy')}
                >
                  <Icon icon={faWifi} label="Test ntfy" />
                </button>
              </div>
            </div>
          </div>
        </>
      ) : null}

      {tab === 'aiops' ? (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>AIOps setup</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            Point Hearth at an agent and a model platform, pick a model, then test. Env vars still
            override any field marked <span className="lock-badge">env</span>.
          </p>
          {aiops.data?.errors?.length ? (
            <div className="panel error-banner">
              <strong>AIOps not ready</strong>
              <ul>
                {aiops.data.errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {aiops.data?.connected ? (
            <div className="panel flash">
              <strong>AIOps connected</strong>
              {aiops.data.agent || aiops.data.model ? (
                <div className="muted">
                  {[aiops.data.agent, aiops.data.model_platform, aiops.data.model]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="wizard-steps">
            <section className="wizard-step">
              <h3>
                <span className="wizard-num">1</span> Enable
              </h3>
              <div className="grid">
                <BoolToggle
                  field={hermes['hermes.enabled']}
                  checked={Boolean(val('hermes.enabled', hermes['hermes.enabled']))}
                  onChange={(v) => setDraft((d) => ({ ...d, 'hermes.enabled': v }))}
                />
                <BoolToggle
                  field={hermes['hermes.auto_triage']}
                  checked={Boolean(val('hermes.auto_triage', hermes['hermes.auto_triage']))}
                  onChange={(v) => setDraft((d) => ({ ...d, 'hermes.auto_triage': v }))}
                />
              </div>
            </section>

            <section className="wizard-step">
              <h3>
                <span className="wizard-num">2</span> Agent
              </h3>
              <div className="grid">
                <SelectField
                  field={hermes['hermes.agent']}
                  value={agentKind}
                  options={AIOPS_AGENTS.map((a) => ({ id: a.id, label: a.label }))}
                  onChange={(v) =>
                    setDraft((d) => ({
                      ...d,
                      'hermes.agent': v,
                      'hermes.provider': v === 'hermes' ? 'agent' : d['hermes.provider'],
                    }))
                  }
                />
                {agentKind === 'hermes' ? (
                  <>
                    <FieldInput
                      field={hermes['hermes.agent_url']}
                      value={String(val('hermes.agent_url', hermes['hermes.agent_url']))}
                      onChange={(v) => setDraft((d) => ({ ...d, 'hermes.agent_url': v }))}
                    />
                    <FieldInput
                      field={hermes['hermes.agent_api_key']}
                      value={String(val('hermes.agent_api_key', hermes['hermes.agent_api_key']))}
                      onChange={(v) => setDraft((d) => ({ ...d, 'hermes.agent_api_key': v }))}
                    />
                  </>
                ) : null}
              </div>
            </section>

            <section className="wizard-step">
              <h3>
                <span className="wizard-num">3</span> Model platform
              </h3>
              <div className="grid">
                <SelectField
                  field={hermes['hermes.model_platform']}
                  value={modelPlatform}
                  options={MODEL_PLATFORMS.map((p) => ({ id: p.id, label: p.label }))}
                  onChange={(v) => setDraft((d) => ({ ...d, 'hermes.model_platform': v }))}
                />
                {modelPlatform === 'ollama' ? (
                  <div className="field-with-action">
                    <FieldInput
                      field={hermes['hermes.ollama_url']}
                      value={ollamaUrl}
                      onChange={(v) => setDraft((d) => ({ ...d, 'hermes.ollama_url': v }))}
                    />
                    <button
                      className="icon-btn"
                      type="button"
                      title="Refresh models"
                      aria-label="Refresh models"
                      disabled={ollamaModels.isFetching || !ollamaUrl.trim()}
                      onClick={() => ollamaModels.refetch()}
                    >
                      <Icon
                        icon={faArrowsRotate}
                        label="Refresh models"
                        spin={ollamaModels.isFetching}
                      />
                    </button>
                  </div>
                ) : null}
                {ollamaModels.isError ? (
                  <div className="error-banner">
                    {(ollamaModels.error as Error).message || 'Failed to list Ollama models'}
                  </div>
                ) : null}
              </div>
            </section>

            <section className="wizard-step">
              <h3>
                <span className="wizard-num">4</span> Model
              </h3>
              <div className="grid">
                {modelOptions.length || selectedModel ? (
                  <SelectField
                    field={hermes['hermes.agent_model']}
                    value={selectedModel}
                    options={
                      modelOptions.length
                        ? modelOptions
                        : selectedModel
                          ? [{ id: selectedModel, label: selectedModel }]
                          : []
                    }
                    onChange={(v) => setDraft((d) => ({ ...d, 'hermes.agent_model': v }))}
                    disabled={!modelOptions.length && !selectedModel}
                  />
                ) : (
                  <div className="field">
                    <label>{hermes['hermes.agent_model']?.label || 'Model'}</label>
                    <div className="muted">
                      {ollamaModels.isFetching
                        ? 'Loading models from Ollama…'
                        : 'No models found. Pull a model in Ollama, then refresh.'}
                    </div>
                  </div>
                )}
              </div>
            </section>
          </div>

          <div className="actions" style={{ marginTop: 16 }}>
            <button
              className="icon-btn primary"
              type="button"
              title="Save AIOps"
              aria-label="Save AIOps"
              onClick={() => {
                const keys = [
                  'hermes.enabled',
                  'hermes.auto_triage',
                  'hermes.agent',
                  'hermes.model_platform',
                  'hermes.ollama_url',
                  'hermes.provider',
                  'hermes.agent_url',
                  'hermes.agent_api_key',
                  'hermes.agent_model',
                ]
                const updates: Record<string, unknown> = {}
                for (const key of keys) {
                  if (key in draft) updates[key] = draft[key]
                  else if (hermes[key] && !hermes[key].locked) updates[key] = val(key, hermes[key])
                }
                if (!hermes['hermes.provider']?.locked) updates['hermes.provider'] = 'agent'
                if (!hermes['hermes.agent']?.locked && !updates['hermes.agent']) {
                  updates['hermes.agent'] = 'hermes'
                }
                if (!hermes['hermes.model_platform']?.locked && !updates['hermes.model_platform']) {
                  updates['hermes.model_platform'] = 'ollama'
                }
                save.mutate(updates)
              }}
            >
              <Icon icon={faFloppyDisk} label="Save AIOps" />
            </button>
            <button
              className="icon-btn"
              type="button"
              title="Test AIOps"
              aria-label="Test AIOps"
              onClick={() => test.mutate('hermes')}
            >
              <Icon icon={faWifi} label="Test AIOps" />
            </button>
          </div>
        </div>
      ) : null}

      {tab === 'auto-raise' ? (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Auto-raise rules</h2>
          <p className="muted">
            Alerts below the minimum severity stay in the inbox until you raise them manually.
            After a fresh volume, defaults reset to <code>critical</code>.
          </p>
          <div className="grid">
            <BoolToggle
              field={autoRaise['auto_raise.enabled']}
              checked={Boolean(val('auto_raise.enabled', autoRaise['auto_raise.enabled']))}
              onChange={(v) => setDraft((d) => ({ ...d, 'auto_raise.enabled': v }))}
            />
            <BoolToggle
              field={autoRaise['auto_raise.group_open']}
              checked={Boolean(val('auto_raise.group_open', autoRaise['auto_raise.group_open']))}
              onChange={(v) => setDraft((d) => ({ ...d, 'auto_raise.group_open': v }))}
            />
            {autoRaise['auto_raise.min_severity'] ? (
              <div className="field">
                <label>{autoRaise['auto_raise.min_severity'].label}</label>
                {autoRaise['auto_raise.min_severity'].hint ? (
                  <div className="muted">{autoRaise['auto_raise.min_severity'].hint}</div>
                ) : null}
                <select
                  value={String(val('auto_raise.min_severity', autoRaise['auto_raise.min_severity']))}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, 'auto_raise.min_severity': e.target.value }))
                  }
                >
                  {['critical', 'warning', 'info', 'unknown'].map((s) => (
                    <option key={s} value={s}>
                      {s} and above
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            <FieldInput
              field={autoRaise['auto_raise.alertnames']}
              value={String(val('auto_raise.alertnames', autoRaise['auto_raise.alertnames']))}
              onChange={(v) => setDraft((d) => ({ ...d, 'auto_raise.alertnames': v }))}
            />
            <FieldInput
              field={autoRaise['auto_raise.label_rules']}
              value={String(val('auto_raise.label_rules', autoRaise['auto_raise.label_rules']))}
              onChange={(v) => setDraft((d) => ({ ...d, 'auto_raise.label_rules': v }))}
            />
            <div className="actions">
              <button
                className="icon-btn primary"
                type="button"
                title="Save auto-raise"
                aria-label="Save auto-raise"
                onClick={() =>
                  saveKeys([
                    'auto_raise.enabled',
                    'auto_raise.group_open',
                    'auto_raise.min_severity',
                    'auto_raise.alertnames',
                    'auto_raise.label_rules',
                  ])
                }
              >
                <Icon icon={faFloppyDisk} label="Save auto-raise" />
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {tab === 'display' ? (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Display</h2>
          <div className="grid">
            <BoolToggle
              field={display['display.show_noise']}
              checked={Boolean(val('display.show_noise', display['display.show_noise']))}
              onChange={(v) => setDraft((d) => ({ ...d, 'display.show_noise': v }))}
            />
            <div className="actions">
              <button
                className="icon-btn primary"
                type="button"
                title="Save display"
                aria-label="Save display"
                onClick={() => saveKeys(['display.show_noise'])}
              >
                <Icon icon={faFloppyDisk} label="Save display" />
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
