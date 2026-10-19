import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { Disclosure } from '@heroui/react'

export function Collapsible({ title, children, open = false, className = '' }: {
  title: ReactNode; children: ReactNode; open?: boolean; className?: string
}) {
  const [expanded, setExpanded] = useState(open)
  useEffect(() => { setExpanded(open) }, [open])
  return <Disclosure className={`app-disclosure ${className}`} isExpanded={expanded} onExpandedChange={setExpanded}>
    <Disclosure.Heading><Disclosure.Trigger className="app-disclosure-trigger">{title}<Disclosure.Indicator /></Disclosure.Trigger></Disclosure.Heading>
    <Disclosure.Content><Disclosure.Body>{children}</Disclosure.Body></Disclosure.Content>
  </Disclosure>
}
