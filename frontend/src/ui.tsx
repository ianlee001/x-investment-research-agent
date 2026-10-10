import { AlertCircle, ArrowUpRight, Check, CheckCheck, Clock3, LoaderCircle, Search, ShieldCheck, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { createContext, useContext, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router-dom'

const LABELS: Record<string, string> = { queued: '排队中', running: '研究中', awaiting_approval: '待你审批', completed: '已完成', partial: '部分完成', failed: '执行失败', cancelled: '已取消', expired: '已过期', pending: '待审批', approved: '已批准', edited: '编辑后批准', rejected: '已拒绝', supported: '证据支持', partially_supported: '部分支持', contradicted: '证据反驳', conflicting: '证据冲突', insufficient_evidence: '证据不足', not_verifiable: '无法核验', executed: '已执行', not_executed: '未执行', not_started: '尚未执行', fact: '事实', prediction: '预测', opinion: '观点', inference: '推断', idle: '已同步', syncing: '同步中', more_pages: '待续页', error: '连接异常' }

export const label = (value: string) => LABELS[value] || value
export function Badge({ status, children }: { status?: string; children?: ReactNode }) {
  return <span className={`badge ${status || ''}`}><span className="badge-dot" />{children || label(status || '')}</span>
}
export function Spinner() { return <div className="loading"><LoaderCircle className="spin" size={20} /><span>正在读取…</span></div> }
export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) { return <div className="notice error"><AlertCircle size={18} /><span>{error instanceof Error ? error.message : '暂时无法读取数据'}</span>{retry && <button onClick={retry} className="text-button">重试</button>}</div> }
export function Empty({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) { return <div className="empty"><div className="empty-icon">{icon || <Search size={27} />}</div><h3>{title}</h3>{description && <p>{description}</p>}{action}</div> }
export function PageTitle({ title, action }: { title: string; action?: ReactNode }) { return <div className="page-heading"><h1>{title}</h1>{action}</div> }
export function Panel({ title, meta, children, className = '' }: { title?: string; meta?: ReactNode; children: ReactNode; className?: string }) { return <section className={`panel ${className}`}>{title && <div className="panel-heading"><h2>{title}</h2>{meta}</div>}{children}</section> }
export function Markdown({ text }: { text: string }) { return <div className="markdown"><ReactMarkdown components={{ a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer noopener">{children}<ArrowUpRight size={12} /></a> }}>{text}</ReactMarkdown></div> }
export function Modal({ title, children, close }: { title: string; children: ReactNode; close: () => void }) { return <div className="modal-backdrop" onClick={close}><section className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()}><div className="panel-heading"><h2>{title}</h2><button className="icon-button" onClick={close} aria-label="关闭"><X size={19} /></button></div>{children}</section></div> }
export function SourceLink({ source, index }: { source: any; index?: number }) { return <a className="source-link" href={source.url} target="_blank" rel="noreferrer noopener"><span className="source-number">{index != null ? String(index + 1).padStart(2, '0') : <ArrowUpRight size={14} />}</span><div><strong>{source.title}</strong><span>{safeHostname(source.url)} · {source.source_type?.toUpperCase()}</span></div><ArrowUpRight size={16} /></a> }
function safeHostname(url: string) { try { return new URL(url).hostname } catch { return '' } }

const ToastContext = createContext<(text: string, error?: boolean) => void>(() => {})
export const useToast = () => useContext(ToastContext)
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(null)
  function show(text: string, error = false) { setToast({ text, error }); window.setTimeout(() => setToast(null), 4500) }
  return <ToastContext.Provider value={show}>{children}{toast && <div className={`toast ${toast.error ? 'error' : ''}`} role="status">{toast.error ? <AlertCircle size={18} /> : <Check size={18} />}{toast.text}</div>}</ToastContext.Provider>
}
