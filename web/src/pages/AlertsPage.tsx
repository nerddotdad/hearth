import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { SeverityBadge, StatusBadge } from '../components/StatusBadge'
import { api, type Alert } from '../lib/api/client'
import {
  faCircleCheck,
  faFire,
  faLayerGroup,
  faMagnifyingGlass,
  faTicket,
} from '../lib/icons'

const STATUSES = [
  { value: '', tip: 'All alerts', icon: faLayerGroup },
  { value: 'firing', tip: 'Firing', icon: faFire },
  { value: 'resolved', tip: 'Resolved', icon: faCircleCheck },
]

function alertTitle(alert: Alert): string {
  return alert.labels?.alertname || alert.fingerprint || 'alert'
}

function alertSeverity(alert: Alert): string {
  return alert.labels?.severity || 'unknown'
}

export function AlertsPage() {
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const qc = useQueryClient()
  const navigate = useNavigate()

  const query = useInfiniteQuery({
    queryKey: ['alerts', status, search],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api.listAlerts({ status, q: search, offset: pageParam, limit: 25 }),
    getNextPageParam: (last) => (last.has_more ? last.next_offset : undefined),
  })

  const alerts = useMemo(
    () => query.data?.pages.flatMap((p) => p.alerts) ?? [],
    [query.data],
  )

  const raise = useMutation({
    mutationFn: () => api.raiseAlerts([...selected]),
    onSuccess: (res) => {
      setSelected(new Set())
      void qc.invalidateQueries({ queryKey: ['alerts'] })
      void qc.invalidateQueries({ queryKey: ['incidents'] })
      if (res.incident?.id) navigate(`/incidents/${res.incident.id}`)
    },
  })

  function toggle(fp: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(fp)) next.delete(fp)
      else next.add(fp)
      return next
    })
  }

  const raiseTip =
    selected.size === 0
      ? 'Select alerts to raise'
      : `Raise incident from ${selected.size} alert${selected.size === 1 ? '' : 's'}`

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
        <button
          className="icon-btn primary"
          type="button"
          disabled={!selected.size || raise.isPending}
          title={raiseTip}
          aria-label={raiseTip}
          onClick={() => raise.mutate()}
        >
          <Icon icon={faTicket} label={raiseTip} />
          {selected.size ? <span className="count">{selected.size}</span> : null}
        </button>
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
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder='status:firing alertname:Homelab* text~"disk"'
            aria-label="Search alerts"
          />
          <button className="icon-btn primary" type="submit" title="Search" aria-label="Search">
            <Icon icon={faMagnifyingGlass} label="Search" />
          </button>
        </form>
      </div>

      {query.isError ? (
        <div className="panel error-banner">{(query.error as Error).message}</div>
      ) : null}
      {raise.isError ? (
        <div className="panel error-banner">{(raise.error as Error).message}</div>
      ) : null}

      <div className="grid">
        {alerts.map((alert) => {
          const fp = alert.fingerprint || ''
          return (
            <label key={fp || alertTitle(alert)} className="incident-row" style={{ cursor: 'pointer' }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <input
                  type="checkbox"
                  checked={selected.has(fp)}
                  disabled={!fp}
                  onChange={() => fp && toggle(fp)}
                />
                <div>
                  <div className="row-title">{alertTitle(alert)}</div>
                  <div className="muted mono">{fp || 'no fingerprint'}</div>
                </div>
              </div>
              <div className="row-meta">
                <StatusBadge status={alert.status} />
                <SeverityBadge severity={alertSeverity(alert)} />
              </div>
              <div className="muted">{alert.updated_at || alert.startsAt || '—'}</div>
              <div className="muted">{alert.labels?.namespace || ''}</div>
            </label>
          )
        })}
      </div>

      {!query.isLoading && alerts.length === 0 ? (
        <div className="panel empty">No alerts match this view.</div>
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
