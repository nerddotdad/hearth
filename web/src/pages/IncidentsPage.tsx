import { useInfiniteQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../components/Icon'
import {
  AgentBadge,
  AlertCountBadge,
  SeverityBadge,
  StatusBadge,
} from '../components/StatusBadge'
import { api } from '../lib/api/client'
import {
  faCircleCheck,
  faCircleExclamation,
  faEye,
  faLayerGroup,
  faMagnifyingGlass,
} from '../lib/icons'

const STATUSES = [
  { value: '', tip: 'All incidents', icon: faLayerGroup },
  { value: 'open', tip: 'Open', icon: faCircleExclamation },
  { value: 'acknowledged', tip: 'Acknowledged', icon: faEye },
  { value: 'resolved', tip: 'Resolved', icon: faCircleCheck },
]

export function IncidentsPage() {
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')

  const query = useInfiniteQuery({
    queryKey: ['incidents', status, search],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api.listIncidents({ status, q: search, offset: pageParam, limit: 25 }),
    getNextPageParam: (last) => (last.has_more ? last.next_offset : undefined),
  })

  const incidents = useMemo(
    () => query.data?.pages.flatMap((p) => p.incidents) ?? [],
    [query.data],
  )

  return (
    <>
      <div className="page-toolbar">
        {STATUSES.map((s) => (
          <button
            key={s.value || 'all'}
            type="button"
            className={`icon-btn ${status === s.value ? 'active' : ''}`}
            title={s.tip}
            aria-label={s.tip}
            aria-pressed={status === s.value}
            onClick={() => setStatus(s.value)}
          >
            <Icon icon={s.icon} label={s.tip} />
          </button>
        ))}
      </div>

      <div className="panel">
        <form
          className="search-row"
          onSubmit={(e) => {
            e.preventDefault()
            setSearch(q.trim())
          }}
        >
          <input
            id="incident-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder='status:open severity>=warning title~"flux"'
            aria-label="Search incidents"
          />
          <button className="icon-btn primary" type="submit" title="Search" aria-label="Search">
            <Icon icon={faMagnifyingGlass} label="Search" />
          </button>
          {search ? (
            <button
              type="button"
              className="icon-btn"
              title="Clear search"
              aria-label="Clear search"
              onClick={() => {
                setQ('')
                setSearch('')
              }}
            >
              Clear
            </button>
          ) : null}
        </form>
      </div>

      {query.isError ? (
        <div className="panel error-banner">{(query.error as Error).message}</div>
      ) : null}

      <div className="grid">
        {incidents.map((inc) => {
          const agentStatus = String(inc.enrichment?.hermes?.status || '')
          return (
            <Link key={inc.id} className="incident-row" to={`/incidents/${inc.id}`}>
              <div>
                <div className="row-title">{inc.title || inc.id}</div>
                <div className="muted mono">{inc.id}</div>
              </div>
              <div className="row-meta">
                <StatusBadge status={inc.status} />
                <SeverityBadge severity={inc.severity} />
                <AgentBadge status={agentStatus} />
              </div>
              <div className="muted" title={inc.updated_at || undefined}>
                {inc.updated_at || '—'}
              </div>
              <AlertCountBadge count={(inc.alerts || []).length} />
            </Link>
          )
        })}
      </div>

      {!query.isLoading && incidents.length === 0 ? (
        <div className="panel empty">No incidents match this view.</div>
      ) : null}

      <div className="actions" style={{ marginTop: 12 }}>
        {query.hasNextPage ? (
          <button type="button" onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>
            {query.isFetchingNextPage ? 'Loading…' : 'Load more'}
          </button>
        ) : null}
      </div>
    </>
  )
}
