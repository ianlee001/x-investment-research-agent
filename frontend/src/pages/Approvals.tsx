import { InitialAvatar, Card, Field, Form, Tabs, AppLink as Link, Button, Badge, Empty, ErrorState, Modal, PageTitle, Spinner, label, useToast } from '../ui'

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Clock3, FilePenLine, ShieldCheck, X } from 'lucide-react'

import { api, formatDate, post } from '../api'

const NAMES: Record<string, string> = { add_to_watchlist: '添加关注标的', save_thesis: '保存投资观点', update_investment_preferences: '更新投资偏好', update_source_trust: '调整来源信任标签' }
const ARG_LABELS: Record<string, string> = { ticker: '股票代码', company_name: '公司名称', notes: '备注', thesis: '研究观点', risk_tolerance: '风险偏好', investment_horizon: '投资期限', username: 'X 用户名', rating: '信任标签', reason: '理由' }

export function ApprovalCard({ approval, compact = false }: { approval: any; compact?: boolean }) {
  const query = useQueryClient(), toast = useToast()
  const [editing, setEditing] = useState(false), [args, setArgs] = useState<Record<string, string>>(approval.args), [rejecting, setRejecting] = useState(false), [reason, setReason] = useState('')
  const mutation = useMutation({ mutationFn: ({ action, body }: { action: string; body?: any }) => post(`/approvals/${approval.id}/${action}`, body), onSuccess: () => { setEditing(false); setRejecting(false); query.invalidateQueries(); toast('审批已记录') }, onError: e => toast(e.message, true) })
  const pending = approval.status === 'pending'
  return <Card className={`approval-card ${compact ? 'compact' : ''}`}><div className="approval-top"><InitialAvatar className="approval-icon"><ShieldCheck size={20} /></InitialAvatar><div><h3>{NAMES[approval.tool_name] || approval.tool_name}</h3><span>{formatDate(approval.created_at)}</span></div><Badge status={approval.status} /></div><dl className="approval-args">{Object.entries(approval.args).filter(([, value]) => value).map(([key, value]) => <div key={key}><dt>{ARG_LABELS[key] || key}</dt><dd>{String(value)}</dd></div>)}</dl>{pending ? <><div className="approval-notice"><Clock3 size={14} />有效至 {formatDate(approval.expires_at)}</div><div className="approval-actions"><Button className="button primary small" disabled={mutation.isPending} onPress={() => mutation.mutate({ action: 'approve' })}><Check size={15} />批准执行</Button><Button className="button secondary small" disabled={mutation.isPending} onPress={() => setEditing(true)}><FilePenLine size={15} />编辑后批准</Button><Button className="button ghost small" disabled={mutation.isPending} onPress={() => setRejecting(true)}><X size={15} />拒绝</Button></div></> : <div className="approval-notice">执行状态：{label(approval.execution_status)}</div>}
    {editing && <Modal title="编辑审批内容" close={() => setEditing(false)}><Form onSubmit={e => { e.preventDefault(); mutation.mutate({ action: 'edit', body: { args } }) }}>{Object.entries(args).map(([key, value]) => <Field label={ARG_LABELS[key] || key} className="field" key={key} value={value} onChange={nextValue => setArgs({ ...args, [key]: nextValue })} rows={4} multiline={['thesis', 'notes', 'reason'].includes(key)} />)}<Button className="button primary full" disabled={mutation.isPending}>保存修改并批准</Button></Form></Modal>}
    {rejecting && <Modal title="拒绝此操作" close={() => setRejecting(false)}><Form onSubmit={e => { e.preventDefault(); mutation.mutate({ action: 'reject', body: { reason } }) }}><Field label="拒绝原因（可选）" multiline className="field" value={reason} onChange={nextValue => setReason(nextValue)} rows={3} placeholder="例如：暂时不加入关注列表" /><Button className="button danger full" disabled={mutation.isPending}>确认拒绝</Button></Form></Modal>}
  </Card>
}

export function Approvals() {
  const [filter, setFilter] = useState('pending')
  const query = useQuery({ queryKey: ['approvals', filter], queryFn: () => api<any[]>(`/approvals?status=${filter}`), refetchInterval: 5000 })
  const content = query.isPending ? <Spinner /> : query.error ? <ErrorState error={query.error} /> : query.data?.length
    ? <div className="approvals-grid">{query.data.map(a => <ApprovalCard approval={a} key={a.id} />)}</div>
    : <Card className="panel"><Empty icon={<ShieldCheck size={32} />} title={filter ? '暂无待审批操作' : '暂无审批记录'} action={<Link to="/chat" className="button secondary">前往研究对话</Link>} /></Card>
  return <div className="page"><PageTitle title="待办审批" />
    <Tabs className="approval-tabs" selectedKey={filter || 'all'} onSelectionChange={key => setFilter(key === 'all' ? '' : String(key))}>
      <Tabs.ListContainer><Tabs.List aria-label="审批记录筛选">
        <Tabs.Tab id="pending">等待审批<Tabs.Indicator /></Tabs.Tab>
        <Tabs.Tab id="all">全部记录<Tabs.Indicator /></Tabs.Tab>
      </Tabs.List></Tabs.ListContainer>
      <Tabs.Panel id="pending">{filter === 'pending' && content}</Tabs.Panel>
      <Tabs.Panel id="all">{filter === '' && content}</Tabs.Panel>
    </Tabs>
  </div>
}
