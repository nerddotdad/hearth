export function StatusBadge({ status }: { status?: string }) {
  const s = (status || 'unknown').toLowerCase()
  return <span className={`badge status-${s}`}>{s}</span>
}

export function SeverityBadge({ severity }: { severity?: string }) {
  const s = (severity || 'unknown').toLowerCase()
  return <span className={`badge severity-${s}`}>{s}</span>
}

/** Hermes investigation state from enrichment.hermes.status */
export function AgentBadge({ status }: { status?: string | null }) {
  const s = (status || '').toLowerCase()
  if (!s) return null
  if (s === 'running') {
    return (
      <span className="badge agent-running" title="Hermes is investigating this incident">
        agent running
      </span>
    )
  }
  if (s === 'complete') {
    return (
      <span className="badge agent-complete" title="Hermes investigation finished">
        agent done
      </span>
    )
  }
  return <span className="badge agent-other">agent {s}</span>
}
