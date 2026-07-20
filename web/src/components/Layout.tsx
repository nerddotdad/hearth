import { NavLink, Outlet } from 'react-router-dom'
import { useLiveUpdates } from '../hooks/useLiveUpdates'
import {
  faBell,
  faGear,
  faPlus,
  faTicket,
  faWifi,
} from '../lib/icons'
import { Icon } from './Icon'

const links = [
  { to: '/', label: 'Incidents', end: true, icon: faTicket },
  { to: '/alerts', label: 'Alerts', icon: faBell },
  { to: '/incidents/new', label: 'New incident', icon: faPlus },
  { to: '/settings', label: 'Settings', icon: faGear },
]

export function Layout() {
  const live = useLiveUpdates()
  const liveTip =
    live === 'live'
      ? 'Live updates connected'
      : live === 'reconnect'
        ? 'Reconnecting live updates…'
        : 'Connecting live updates…'

  return (
    <div className="wrap">
      <header className="site-header">
        <div>
          <h1>
            <NavLink to="/" className="brand-link">
              Hearth
            </NavLink>
          </h1>
          <div className="muted">Homelab incident desk</div>
        </div>
        <div className="header-right">
          <span className={`live-pill live-${live}`} title={liveTip} aria-label={liveTip}>
            <Icon icon={faWifi} label={liveTip} />
          </span>
          <nav className="site-nav" aria-label="Primary">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                title={link.label}
                aria-label={link.label}
                className={({ isActive }) => (isActive ? 'active' : undefined)}
              >
                <Icon icon={link.icon} label={link.label} />
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
