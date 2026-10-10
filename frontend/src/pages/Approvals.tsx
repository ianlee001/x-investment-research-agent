import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Clock3, ExternalLink, FilePenLine, ShieldCheck, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, formatDate, post } from '../api'
import { Badge, Empty, ErrorState, Modal, PageTitle, Spinner, label, useToast } from '../ui'

const NAMES: Record<string, string> = { add_to_watchlist: '添加关注标的', save_thesis: '保存投资观点', update_investment_preferences: '更新投资偏好', update_source_trust: '调整来源信任标签' }
const ARG_LABELS: Record<string, string> = { ticker: '股票代码', company_name: '公司名称', notes: '备注', thesis: '研究观点', risk_tolerance: '风险偏好', investment_horizon: '投资期限', username: 'X 用户名', rating: '信任标签', reason: '理由' }

export function ApprovalCard({ approval, compact = false }: { approval: any; compact?: boolean }) {
  const query = useQueryClient(), toast = useToast()
  const [editing, setEditing] = useState(false), [args, setArgs] = useState<Record<string, string>>(approval.args), [rejecting, setRejecting] = useState(false), [reason, setReason] = useState('')
  const mutation = useMutation({ mutationFn: ({ action, body }: { action: string; body?: any }) => post(`/approvals/${approval.id}/${action}`, body), onSuccess: () => { setEditing(false); setRejecting(false); query.invalidateQueries(); toast('审批已记录') }, onError: e => toast(e.message, true) })
  const pending = approval.status === 'pending'
  return <article className={`approval-card ${compact ? 'compact' : ''}`}><div className="approval-top"><span className="approval-icon"><ShieldCheck size={20} /></span><div><h3>{NAMES[approval.tool_name] || approval.tool_name}</h3><span>{formatDate(approval.created_at)}</span></div><Badge status={approval.status} /></div><dl className="approval-args">{Object.entries(approval.args).filter(([, value]) => value).map(([key, value]) => <div key={key}><dt>{ARG_LABELS[key] || key}</dt><dd>{String(value)}</dd></div>)}</dl>{pending ? <><div className="approval-notice"><Clock3 size={14} />有效至 {formatDate(approval.expires_at)}</div><div className="approval-actions"><button className="button primary small" disabled={mutation.isPending} onClick={() => mutation.mutate({ action: 'approve' })}><Check size={15} />批准执行</button><button className="button secondary small" disabled={mutation.isPending} onClick={() => setEditing(true)}><FilePenLine size={15} />编辑后批准</button><button className="button ghost small" disabled={mutation.isPending} onClick={() => setRejecting(true)}><X size={15} />拒绝</button></div></> : <div className="approval-notice">执行状态：{label(approval.execution_status)}</div>}
    {editing && <Modal title="编辑审批内容" close={() => setEditing(false)}><form onSubmit={e => { e.preventDefault(); mutation.mutate({ action: 'edit', body: { args } }) }}>{Object.entries(args).map(([key, value]) => <label className="field" key={key}>{ARG_LABELS[key] || key}{['thesis', 'notes', 'reason'].includes(key) ? <textarea value={value} onChange={e => setArgs({ ...args, [key]: e.target.value })} rows={4} /> : <input value={value} onChange={e => setArgs({ ...args, [key]: e.target.value })} />}</label>)}<button className="button primary full" disabled={mutation.isPending}>保存修改并批准</button></form></Modal>}
    {rejecting && <Modal title="拒绝此操作" close={() => setRejecting(false)}><form onSubmit={e => { e.preventDefault(); mutation.mutate({ action: 'reject', body: { reason } }) }}><label className="field">拒绝原因（可选）<textarea value={reason} onChange={e => setReason(e.target.value)} rows={3} placeholder="例如：暂时不加入关注列表" /></label><button className="button danger full" disabled={mutation.isPending}>确认拒绝</button></form></Modal>}
  </article>
}

export function Approvals() {
  const [filter, setFilter] = useState('pending')
  const query = useQuery({ queryKey: ['approvals', filter], queryFn: () => api<any[]>(`/approvals?status=${filter}`), refetchInterval: 5000 })
  return <div className="page"><PageTitle title="待办审批" /><div className="tabs">{[{ value: 'pending', name: '等待审批' }, { value: '', name: '全部记录' }].map(t => <button key={t.value} onClick={() => setFilter(t.value)} className={filter === t.value ? 'selected' : ''}>{t.name}{t.value === 'pending' && filter === 'pending' && <span>{query.data?.length || 0}</span>}</button>)}</div>{query.isPending ? <Spinner /> : query.error ? <ErrorState error={query.error} /> : query.data?.length ? <div className="approvals-grid">{query.data.map(a => <ApprovalCard approval={a} key={a.id} />)}</div> : <div className="panel"><Empty icon={<ShieldCheck size={32} />} title={filter ? '暂无待审批操作' : '暂无审批记录'} action={<Link to="/chat" className="button secondary">前往研究对话</Link>} /></div>}</div>
}
