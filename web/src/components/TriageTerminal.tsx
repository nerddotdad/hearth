import { useCallback, useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { api, sseUrl } from '../lib/api/client'
import { Icon } from './Icon'
import { faTerminal, faXmark, faArrowsRotate } from '../lib/icons'

type SandboxStatus = {
  incident_id?: string
  status?: string
  pod_name?: string
  expires_at?: string
  backend?: string
  enabled?: boolean
  error?: string
}

type Props = {
  incidentId: string
}

function terminalWsUrl(incidentId: string): string {
  const path = `/api/incidents/${encodeURIComponent(incidentId)}/sandbox/terminal`
  const url = new URL(sseUrl(path), window.location.origin)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

export function TriageTerminal({ incidentId }: Props) {
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState<SandboxStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const hostRef = useRef<HTMLDivElement | null>(null)
  const termRef = useRef<Terminal | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const fitRef = useRef<FitAddon | null>(null)

  const refreshStatus = useCallback(async () => {
    try {
      const s = await api.getSandbox(incidentId)
      setStatus(s)
    } catch (e) {
      setStatus({ status: 'error', error: (e as Error).message })
    }
  }, [incidentId])

  useEffect(() => {
    void refreshStatus()
  }, [refreshStatus])

  const disconnect = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    termRef.current?.dispose()
    termRef.current = null
    fitRef.current = null
  }, [])

  useEffect(() => {
    if (!open) {
      disconnect()
      return
    }
    let cancelled = false
    const boot = async () => {
      setBusy(true)
      setError(null)
      try {
        await api.ensureSandbox(incidentId)
        await refreshStatus()
        if (cancelled || !hostRef.current) return

        const term = new Terminal({
          cursorBlink: true,
          fontSize: 13,
          theme: { background: '#0d1117', foreground: '#e6edf3' },
        })
        const fit = new FitAddon()
        term.loadAddon(fit)
        term.open(hostRef.current)
        fit.fit()
        termRef.current = term
        fitRef.current = fit

        const ws = new WebSocket(terminalWsUrl(incidentId))
        ws.binaryType = 'arraybuffer'
        wsRef.current = ws
        ws.onopen = () => {
          term.writeln('\r\nConnected to incident triage sandbox.\r\n')
          fit.fit()
        }
        ws.onmessage = (ev) => {
          if (typeof ev.data === 'string') {
            term.write(ev.data)
          } else {
            term.write(new Uint8Array(ev.data as ArrayBuffer))
          }
        }
        ws.onerror = () => setError('Terminal WebSocket error')
        ws.onclose = () => term.writeln('\r\n\x1b[90m[disconnected]\x1b[0m\r\n')
        term.onData((data) => {
          if (ws.readyState === WebSocket.OPEN) ws.send(data)
        })

        const onResize = () => fit.fit()
        window.addEventListener('resize', onResize)
        return () => window.removeEventListener('resize', onResize)
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setBusy(false)
      }
    }
    void boot()
    return () => {
      cancelled = true
      disconnect()
    }
  }, [open, incidentId, disconnect, refreshStatus])

  const destroy = async () => {
    setBusy(true)
    try {
      await api.destroySandbox(incidentId)
      setOpen(false)
      await refreshStatus()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const sandboxState = status?.status || 'absent'

  return (
    <div className="panel" id="sandbox">
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <div>
          <h3 style={{ margin: 0 }}>Triage sandbox</h3>
          <div className="muted mono" style={{ marginTop: 4 }}>
            {sandboxState}
            {status?.pod_name ? ` · ${status.pod_name}` : ''}
            {status?.expires_at ? ` · expires ${status.expires_at}` : ''}
          </div>
        </div>
        <div className="actions">
          <button
            className="icon-btn primary"
            type="button"
            title={open ? 'Close terminal' : 'Open terminal'}
            aria-label={open ? 'Close terminal' : 'Open terminal'}
            disabled={busy || status?.enabled === false}
            onClick={() => setOpen((v) => !v)}
          >
            <Icon icon={open ? faXmark : faTerminal} label={open ? 'Close' : 'Terminal'} />
          </button>
          <button
            className="icon-btn"
            type="button"
            title="Refresh status"
            aria-label="Refresh status"
            disabled={busy}
            onClick={() => void refreshStatus()}
          >
            <Icon icon={faArrowsRotate} label="Refresh" />
          </button>
          {sandboxState === 'ready' ? (
            <button type="button" className="icon-btn" disabled={busy} onClick={() => void destroy()}>
              Destroy
            </button>
          ) : null}
        </div>
      </div>

      {status?.enabled === false ? (
        <div className="muted" style={{ marginTop: 8 }}>
          Sandbox is disabled. Enable via Settings or HEARTH_SANDBOX_ENABLED.
        </div>
      ) : null}

      {error ? (
        <div className="error-banner panel" style={{ marginTop: 12 }}>
          {error}
        </div>
      ) : null}

      {open ? (
        <div
          ref={hostRef}
          className="triage-terminal"
          style={{
            marginTop: 12,
            height: 320,
            padding: 8,
            background: '#0d1117',
            borderRadius: 8,
            overflow: 'hidden',
          }}
        />
      ) : (
        <p className="muted" style={{ marginBottom: 0, marginTop: 8 }}>
          Same environment the LLM agent uses for kubectl/flux triage. Opens an interactive shell in
          the incident sandbox.
        </p>
      )}
    </div>
  )
}
