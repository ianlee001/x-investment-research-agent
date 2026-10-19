import { ArrowUpRight, Search } from 'lucide-react'
import type { ReactNode, ComponentPropsWithoutRef, ComponentPropsWithRef } from 'react'
import { useCallback } from 'react'

import { Alert, Avatar, Button as HeroButton, Card, Chip, CloseButton, Link as HeroLink, Modal as HeroModal, Spinner as HeroSpinner, Surface, Toast, Tooltip, toast } from '@heroui/react'
import ReactMarkdown from 'react-markdown'
import { Link as RouterLink } from 'react-router-dom'
import { citationPlugin } from './citations'
import { publicSourceUrl, type ResearchSource } from './sources'
export { SourceLink } from './sources'
export { Field, SearchInput, SelectInput, NumberInput } from './components/fields'
export { Collapsible } from './components/Collapsible'
export { Card, Surface as Container, Form, Link as ExternalLink, Pagination, ScrollShadow, Tabs } from '@heroui/react'

const LABELS: Record<string, string> = { queued: '排队中', running: '研究中', awaiting_approval: '待你审批', completed: '已完成', partial: '部分完成', failed: '执行失败', cancelled: '已取消', expired: '已过期', pending: '待审批', approved: '已批准', edited: '编辑后批准', rejected: '已拒绝', supported: '证据支持', partially_supported: '部分支持', contradicted: '证据反驳', conflicting: '证据冲突', insufficient_evidence: '证据不足', not_verifiable: '无法核验', executed: '已执行', not_executed: '未执行', not_started: '尚未执行', fact: '事实', prediction: '预测', opinion: '观点', inference: '推断', idle: '已同步', syncing: '同步中', more_pages: '待续页', error: '连接异常' }

export const label = (value: string) => LABELS[value] || value
// Keep native form submission semantics while sharing HeroUI's keyboard/press behavior.
export function Button({ disabled, isDisabled, title, type = 'submit', className = '', variant, size, isIconOnly, ...props }: ComponentPropsWithoutRef<typeof HeroButton> & { disabled?: boolean; title?: string }) {
  const classes = typeof className === 'string' ? className : ''
  const semantic = variant || (/\bdanger\b/.test(classes) ? 'danger' : /\bsecondary\b/.test(classes) ? 'secondary' : /\b(primary|send-button)\b/.test(classes) ? 'primary' : 'ghost')
  const iconOnly = isIconOnly ?? /\b(icon-button|send-button)\b/.test(classes)
  const hint = title || (iconOnly ? props['aria-label'] : undefined)
  const button = <HeroButton {...props} type={type} isDisabled={disabled || isDisabled} className={className}
    variant={semantic} size={size || (/\bsmall\b/.test(classes) ? 'sm' : 'md')} isIconOnly={iconOnly} />
  return hint && !(disabled || isDisabled) ? <Tooltip delay={500}>{button}<Tooltip.Content className="app-tooltip">{hint}</Tooltip.Content></Tooltip> : button
}
export function AppLink({ to, ...props }: Omit<ComponentPropsWithoutRef<typeof HeroLink>, 'href' | 'render'> & { to: string }) {
  // Supplying href makes HeroUI render an anchor; keep its press/focus props on the Router anchor.
  return <HeroLink {...props} href={to} render={attributes => <RouterLink {...attributes as ComponentPropsWithRef<'a'>} to={to} />} />
}
export function InitialAvatar({ children, className = '', label: accessibleLabel }: { children: ReactNode; className?: string; label?: string }) {
  return <Avatar className={className} aria-label={accessibleLabel}><Avatar.Fallback>{children}</Avatar.Fallback></Avatar>
}
export function Badge({ status, children }: { status?: string; children?: ReactNode }) {
  return <Chip size="sm" className={`badge ${status || ''}`}><span className="badge-dot" />{children || label(status || '')}</Chip>
}
export function Spinner() { return <div className="loading"><HeroSpinner size="sm" aria-label="正在读取" /><span>正在读取…</span></div> }
export function Notice({ children, className = 'notice' }: { children: ReactNode; className?: string }) {
  return <Alert className={className} status={className.includes('error') ? 'danger' : className.includes('warning') ? 'warning' : 'default'}>
    <Alert.Indicator /><Alert.Content><Alert.Description>{children}</Alert.Description></Alert.Content>
  </Alert>
}
export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) { return <Alert className="notice error" status="danger"><Alert.Indicator /><Alert.Content><Alert.Description>{error instanceof Error ? error.message : '暂时无法读取数据'}</Alert.Description></Alert.Content>{retry && <Button onPress={retry} className="text-button">重试</Button>}</Alert> }
export function Empty({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) { return <Surface className="empty"><InitialAvatar className="empty-icon">{icon || <Search size={27} />}</InitialAvatar><h3>{title}</h3>{description && <p>{description}</p>}{action}</Surface> }
export function PageTitle({ title, action }: { title: string; action?: ReactNode }) { return <div className="page-heading"><h1>{title}</h1>{action}</div> }
export function Panel({ title, meta, children, className = '' }: { title?: string; meta?: ReactNode; children: ReactNode; className?: string }) { return <Card className={`panel ${className}`}>{title && <Card.Header className="panel-heading"><h2>{title}</h2>{meta}</Card.Header>}<Card.Content className="panel-content">{children}</Card.Content></Card> }
export function Markdown({ text, sources, citationScope = 'report', pending = false }: {
  text: string; sources?: ResearchSource[]; citationScope?: string; pending?: boolean
}) {
  return <div className="markdown"><ReactMarkdown remarkPlugins={sources ? [citationPlugin(sources, citationScope, pending)] : []}
    components={{ a: ({ children, href }) => {
      if (href === '#unresolved-citation') return <span className="citation-unresolved">{children}</span>
      if (href?.startsWith(`#${citationScope}-source-`)) return <HeroLink className="citation-link" href={href}>{children}</HeroLink>
      const url = publicSourceUrl(href)
      return url ? <HeroLink href={url} target="_blank" rel="noreferrer noopener">{children}<ArrowUpRight size={12} /></HeroLink> : <span>{children}</span>
    } }}>{text}</ReactMarkdown></div>
}
export function Modal({ title, children, close }: { title: string; children: ReactNode; close: () => void }) {
  return <HeroModal.Backdrop isOpen onOpenChange={open => { if (!open) close() }} className="app-modal-backdrop">
    <HeroModal.Container placement="center" size="md"><HeroModal.Dialog className="app-modal" aria-label={title}>
      <HeroModal.Header className="panel-heading"><HeroModal.Heading>{title}</HeroModal.Heading><CloseButton onPress={close} aria-label="关闭" /></HeroModal.Header>
      <HeroModal.Body>{children}</HeroModal.Body>
    </HeroModal.Dialog></HeroModal.Container>
  </HeroModal.Backdrop>
}

export function DeleteHistoryDialog({ kind, name, pending, error, confirm, close }: {
  kind: 'research' | 'chat'; name: string; pending: boolean; error: unknown; confirm: () => void; close: () => void
}) {
  return <Modal title={kind === 'research' ? '删除研究记录' : '删除研究对话'} close={() => { if (!pending) close() }}>
    <p className="delete-history-name">{name}</p>
    <p className="form-note">{kind === 'research' ? '将永久删除这份研究及其报告、来源和活动记录，无法恢复。' : '将永久删除此对话的全部消息与研究记录，无法恢复。已保存的关注和偏好会保留。'}</p>
    {!!error && <ErrorState error={error} />}
    <div className="modal-actions"><Button className="button secondary" autoFocus disabled={pending} onPress={close}>取消</Button>
      <Button className="button danger" disabled={pending} onPress={confirm}>{pending ? '删除中…' : '确认删除'}</Button></div>
  </Modal>
}

export const useToast = () => useCallback((text: string, error = false) => {
  toast.clear()
  if (error) toast.danger(text, { timeout: 4500 })
  else toast.success(text, { timeout: 4500 })
}, [])
export function ToastProvider({ children }: { children: ReactNode }) {
  return <>{children}<Toast.Provider placement="bottom" maxVisibleToasts={1} /></>
}
