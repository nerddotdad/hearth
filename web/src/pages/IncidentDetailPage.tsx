import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { SeverityBadge, StatusBadge } from '../components/StatusBadge'
import { useAgentSession } from '../hooks/useAgentSession'
import { api, hermesChatUrl } from '../lib/api/client'
import {
  faArrowUpRightFromSquare,
  faCircleCheck,
  faRobot,
  faRotate,
} from '../lib/icons'

export function IncidentDetailPage() {
  const { id = '' } = useParams()
  const qc = useQueryClient()
  const [note, setNote] = useState('')

  const query = useQuery({
    queryKey: ['incident', id],
    queryFn: () => api.getIncident(id),
    enabled: Boolean(id),
  })

  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.getSettings(),
  })

  const hermes = query.data?.enrichment?.hermes || {}
  const agent = useAgentSession(id, hermes)

  const hermesBase = useMemo(() => {
    const field = settings.data?.groups?.hermes?.find((f) => f.key === 'hermes.public_base_url')
    return field ? String(field.value || '') : ''
  }, [settings.data])

  const hermesEnabled = useMemo(() => {
    const field = settings.data?.groups?.hermes?.find((f) => f.key === 'hermes.enabled')
    if (!field) return true
    return Boolean(field.raw_value ?? field.value)
  }, [settings.data])

  const openInHermesUrl = hermesChatUrl(hermesBase, hermes.session_id as string | undefined)

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['incident', id] })
    void qc.invalidateQueries({ queryKey: ['incidents'] })
  }

  const ack = useMutation({
    mutationFn: () => api.ack(id),
    onSuccess: invalidate,
  })
  const resolve = useMutation({
    mutationFn: () => api.resolve(id),
    onSuccess: invalidate,
  })
  const investigate = useMutation({
    mutationFn: (force: boolean) => api.investigate(id, force),
    onSuccess: invalidate,
  })
  const addNote = useMutation({
    mutationFn: () => api.addNote(id, note),
    onSuccess: () => {
      setNote('')
      invalidate()
    },
  })

  if (query.isLoading) {
    return <div className="panel muted">Loading incident…</div>
  }
  if (query.isError || !query.data) {
    return (
      <div className="panel error-banner">
        {(query.error as Error)?.message || 'Incident not found'}{' '}
        <Link to="/">Back to incidents</Link>
      </div>
    )
  }

  const incident = query.data
  const status = (incident.status || 'open').toLowerCase()
  const tags = incident.enrichment?.tags || []
  const notes = incident.enrichment?.notes || []
  const sessionId = String(hermes.session_id || '')

  return (
    <>
      <div className="panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <h2 style={{ margin: '0 0 8px' }}>{incident.title || incident.id}</h2>
            <div className="muted mono">
              {incident.id} · updated {incident.updated_at || '—'}
            </div>
            <div style={{ marginTop: 8 }} className="actions">
              <StatusBadge status={incident.status} />
              <SeverityBadge severity={incident.severity} />
              {incident.enrichment?.manual ? <span className="badge">manual</span> : null}
            </div>
          </div>
          <div className="actions">
            {status === 'open' ? (
              <button className="primary" type="button" onClick={() => ack.mutate()} disabled={ack.isPending}>
                <Icon icon={faRotate} /> Acknowledge
              </button>
            ) : null}
            {status === 'open' || status === 'acknowledged' ? (
              <button type="button" onClick={() => resolve.mutate()} disabled={resolve.isPending}>
                <Icon icon={faCircleCheck} /> Resolve
              </button>
            ) : null}
          </div>
        </div>
        {incident.summary ? <p>{incident.summary}</p> : null}
        {tags.length ? <p className="muted">Tags: {tags.join(', ')}</p> : null}
        {incident.merged_into_id ? (
          <p>
            Merged into <Link to={`/incidents/${incident.merged_into_id}`}>{incident.merged_into_id}</Link>
          </p>
        ) : null}
      </div>

      <div className="panel" id="agent">
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: 12,
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          <h3 style={{ margin: 0 }}>Agent</h3>
          <div className="actions">
            {hermesEnabled ? (
              <>
                <button
                  className="primary"
                  type="button"
                  onClick={() => investigate.mutate(false)}
                  disabled={investigate.isPending}
                >
                  <Icon icon={faRobot} /> Investigate
                </button>
                {sessionId ? (
                  <button
                    type="button"
                    onClick={() => investigate.mutate(true)}
                    disabled={investigate.isPending}
                  >
                    New investigation
                  </button>
                ) : null}
              </>
            ) : null}
            {openInHermesUrl ? (
              <a className="btn" href={openInHermesUrl} target="_blank" rel="noopener noreferrer">
                <Icon icon={faArrowUpRightFromSquare} /> Open in Hermes
              </a>
            ) : null}
          </div>
        </div>

        {!hermesEnabled ? (
          <div className="agent-status">
            Hermes integration is disabled. Configure it in <Link to="/settings#aiops">Settings</Link>.
          </div>
        ) : (
          <div className="agent-status">{agent.statusText}</div>
        )}

        {sessionId ? (
          <div className="muted mono" style={{ marginTop: 6 }}>
            session {sessionId}
          </div>
        ) : null}

        {investigate.isError ? (
          <div className="error-banner panel" style={{ marginTop: 12 }}>
            {(investigate.error as Error).message}
          </div>
        ) : null}

        {agent.error && sessionId ? (
          <div className="error-banner panel" style={{ marginTop: 12 }}>
            {agent.error}
          </div>
        ) : null}

        {sessionId ? (
          <div className="agent-feed" style={{ marginTop: 12 }}>
            {agent.messages.length ? (
              agent.messages.map((msg, i) => (
                <div key={`${msg.role}-${i}`} className={`agent-msg ${msg.role || 'message'}`}>
                  <div className="role">{msg.role || 'message'}</div>
                  <div>{msg.content || ''}</div>
                </div>
              ))
            ) : (
              <div className="muted">No agent messages yet.</div>
            )}
          </div>
        ) : null}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>Alerts ({(incident.alerts || []).length})</h3>
        <div className="grid">
          {(incident.alerts || []).map((alert) => (
            <div key={alert.fingerprint || alert.labels?.alertname} className="panel" style={{ margin: 0 }}>
              <strong>{alert.labels?.alertname || 'alert'}</strong> · {alert.status}
              <div className="muted mono">{alert.fingerprint}</div>
              <div>{alert.annotations?.description || alert.annotations?.summary || ''}</div>
            </div>
          ))}
          {!incident.alerts?.length ? <div className="muted">No alerts attached.</div> : null}
        </div>
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>Add note</h3>
        <form
          className="grid"
          onSubmit={(e) => {
            e.preventDefault()
            if (note.trim()) addNote.mutate()
          }}
        >
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What did you try? What worked?"
            required
          />
          <div className="actions">
            <button type="submit" disabled={addNote.isPending}>
              Add note
            </button>
          </div>
        </form>
        <div className="grid" style={{ marginTop: 16 }}>
          {notes.map((n, i) => (
            <div key={`${n.created_at}-${i}`}>
              <div>{n.body}</div>
              <div className="muted">
                {n.actor} · {n.created_at}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>Timeline</h3>
        <div className="grid">
          {(incident.events || []).map((ev, i) => (
            <div key={`${ev.created_at}-${i}`}>
              <strong>{ev.event_type}</strong> <span className="muted">{ev.created_at}</span>
              <div className="muted">{ev.actor}</div>
            </div>
          ))}
          {!incident.events?.length ? <div className="muted">No events yet.</div> : null}
        </div>
      </div>
    </>
  )
}
