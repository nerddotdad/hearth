import { useEffect, useState } from 'react'
import { api, type AgentMessage } from '../lib/api/client'

type AgentFeedState = {
  messages: AgentMessage[]
  statusText: string
  error: string | null
}

/**
 * Mirror legacy ui.py agent panel: poll Hermes transcript via /agent/session,
 * and while status=running subscribe to /agent/stream SSE for live refresh.
 */
export function useAgentSession(
  incidentId: string,
  hermes: { session_id?: unknown; stream_id?: unknown; status?: unknown },
): AgentFeedState {
  const sessionId = String(hermes.session_id || '')
  const streamId = String(hermes.stream_id || '')
  const hermesStatus = String(hermes.status || '')

  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [statusText, setStatusText] = useState(
    sessionId
      ? `Status: ${hermesStatus || 'unknown'}`
      : 'No agent session yet — Investigate or send a chat message.',
  )
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!incidentId || !sessionId) {
      setMessages([])
      setError(null)
      setStatusText('No agent session yet — Investigate or send a chat message.')
      return
    }

    let cancelled = false
    let source: EventSource | null = null
    let pollTimer: number | undefined

    const refreshSession = async () => {
      try {
        const data = await api.getAgentSession(incidentId)
        if (cancelled) return
        const msgs = data.messages || []
        setMessages(msgs)
        setError(null)
        setStatusText(
          data.status === 'running'
            ? 'Agent is working…'
            : msgs.length
              ? 'Ready — ask a follow-up about this incident'
              : 'Waiting for agent output',
        )
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Could not load agent feed')
        setStatusText(`Could not load agent feed: ${err instanceof Error ? err.message : 'error'}`)
      }
    }

    void refreshSession()

    if (streamId && hermesStatus === 'running') {
      setStatusText('Streaming agent response…')
      source = new EventSource(api.agentStreamUrl(incidentId, streamId))
      const onUpdate = () => {
        void refreshSession()
      }
      source.onmessage = onUpdate
      source.addEventListener('agent', onUpdate)
      source.addEventListener('end', () => {
        source?.close()
        void refreshSession()
      })
      source.onerror = () => {
        source?.close()
        void refreshSession()
      }
      // hearth-agent stores messages on the incident — poll while streaming.
      if (streamId.startsWith('agent:')) {
        pollTimer = window.setInterval(() => {
          void refreshSession()
        }, 2000)
      }
    } else {
      pollTimer = window.setInterval(() => {
        void refreshSession()
      }, 5000)
    }

    return () => {
      cancelled = true
      source?.close()
      if (pollTimer) window.clearInterval(pollTimer)
    }
  }, [incidentId, sessionId, streamId, hermesStatus])

  return { messages, statusText, error }
}
