import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import {
  faBell,
  faCircleCheck,
  faCircleExclamation,
  faCircleInfo,
  faEye,
  faFire,
  faQuestion,
  faRobot,
  faTriangleExclamation,
} from '@fortawesome/free-solid-svg-icons'
import { Icon } from './Icon'

type TipIconProps = {
  icon: IconDefinition
  tip: string
  className?: string
  spin?: boolean
}

function TipIcon({ icon, tip, className, spin }: TipIconProps) {
  return (
    <span className={`icon-badge ${className || ''}`} title={tip} aria-label={tip}>
      <Icon icon={icon} spin={spin} label={tip} />
    </span>
  )
}

const STATUS: Record<string, { icon: IconDefinition; tip: string; className: string }> = {
  open: { icon: faCircleExclamation, tip: 'Open', className: 'status-open' },
  acknowledged: { icon: faEye, tip: 'Acknowledged', className: 'status-acknowledged' },
  resolved: { icon: faCircleCheck, tip: 'Resolved', className: 'status-resolved' },
  firing: { icon: faFire, tip: 'Firing', className: 'status-firing' },
}

export function StatusBadge({ status }: { status?: string }) {
  const s = (status || 'unknown').toLowerCase()
  const conf = STATUS[s]
  if (!conf) {
    return <TipIcon icon={faCircleInfo} tip={s} className="status-unknown" />
  }
  return <TipIcon icon={conf.icon} tip={conf.tip} className={conf.className} />
}

const SEVERITY: Record<string, { icon: IconDefinition; tip: string; className: string }> = {
  critical: { icon: faFire, tip: 'Critical', className: 'severity-critical' },
  warning: { icon: faTriangleExclamation, tip: 'Warning', className: 'severity-warning' },
  info: { icon: faCircleInfo, tip: 'Info', className: 'severity-info' },
}

export function SeverityBadge({ severity }: { severity?: string }) {
  const s = (severity || 'unknown').toLowerCase()
  const conf = SEVERITY[s]
  if (!conf) {
    return <TipIcon icon={faQuestion} tip={`Severity: ${s}`} className="severity-unknown" />
  }
  return <TipIcon icon={conf.icon} tip={conf.tip} className={conf.className} />
}

/** Hermes investigation state from enrichment.hermes.status */
export function AgentBadge({ status }: { status?: string | null }) {
  const s = (status || '').toLowerCase()
  if (!s) return null
  if (s === 'running') {
    return (
      <TipIcon
        icon={faRobot}
        tip="Agent processing"
        className="agent-running"
        spin
      />
    )
  }
  if (s === 'complete') {
    return <TipIcon icon={faRobot} tip="Agent complete" className="agent-complete" />
  }
  return <TipIcon icon={faRobot} tip={`Agent: ${s}`} className="agent-other" />
}

export function AlertCountBadge({ count }: { count: number }) {
  const tip = count === 1 ? '1 alert' : `${count} alerts`
  return (
    <span className="icon-badge count-badge" title={tip} aria-label={tip}>
      <Icon icon={faBell} label={tip} />
      <span className="count">{count}</span>
    </span>
  )
}
