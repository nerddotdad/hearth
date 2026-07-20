import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'

type Props = {
  icon: IconDefinition
  className?: string
  title?: string
  spin?: boolean
  /** Accessible name when the icon stands alone */
  label?: string
}

export function Icon({ icon, className, title, spin, label }: Props) {
  return (
    <FontAwesomeIcon
      icon={icon}
      className={className}
      title={title}
      spin={spin}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? 'img' : undefined}
    />
  )
}
