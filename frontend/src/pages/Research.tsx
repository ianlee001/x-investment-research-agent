import { InitialAvatar, Card, Collapsible, Container, Field, Form, Notice, Button, Badge, DeleteHistoryDialog, ErrorState, Markdown, PageTitle, Spinner, label, useToast } from '../ui'

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { ArrowDownToLine, ArrowRight, ArrowUpRight, Clock3, LoaderCircle, Plus, Search, ShieldCheck, Sparkles, Square, Trash2, TrendingDown, TrendingUp } from 'lucide-react'
import { api, formatDate, isActive, post, remove, requestKey, type Run } from '../api'
import { useRunEvents } from '../hooks'

import { ApprovalCard } from './Approvals'
import { DataSnapshot, isDataSource, SourceList, SourceReference } from '../sources'

export function ReportView({ report }: { report: any }) {
  const sourceMap = Object.fromEntries((report.sources || []).map((s: any) => [s.id, s]))
  function download() { const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'research-report.json'; a.click(); URL.revokeObjectURL(url) }
  return <div className="report"><div className="report-topline"><Button className="icon-button" onPress={download} aria-label="导出研究报告"><ArrowDownToLine size={17} /></Button></div><h2>{report.title}</h2><div className="report-meta"><Clock3 size={13} />{formatDate(report.generated_at)}<span>·</span><span>信息截止：{report.data_cutoff || '见各来源'}</span></div><section className="report-summary"><h3>研究摘要</h3><Markdown text={report.summary || ''} sources={report.sources || []} /></section>{report.assessment && <Container className="assessment"><ShieldCheck size={20} /><div><strong>当前判断</strong><Markdown text={report.assessment} sources={report.sources || []} /></div></Container>}
    {report.coverage && <Container className="coverage-strip"><div><strong>{report.coverage.claims}</strong><span>关键断言</span></div><div><strong>{report.coverage.sources}</strong><span>记录来源</span></div><div><strong>{report.coverage.supported}</strong><span>证据支持</span></div><div><strong>{report.coverage.unresolved}</strong><span>仍待核验</span></div></Container>}
    {!!report.claims?.length && <section className="report-section"><h3>关键断言</h3><div className="claims">{report.claims.map((claim: any, index: number) => <Collapsible className="claim-card" key={claim.claim_id} open={index === 0} title={<><span className="claim-number">{String(index + 1).padStart(2, '0')}</span><span className="claim-text">{claim.text}<small>{label(claim.kind)}{claim.period && ` · ${claim.period}`}{claim.unit && ` · ${claim.unit}`}</small></span><Badge status={claim.status} /></>}><div className="claim-body"><Markdown text={claim.explanation || ''} sources={report.sources || []} /><div className="claim-evidence-meta">核验来源 {claim.evidence_strength?.verifying_sources || 0} · 一手来源 {claim.evidence_strength?.primary_sources || 0} · 不同域名 {claim.evidence_strength?.distinct_hosts || 0}</div>{claim.evidence?.map((e: any, n: number) => <Container className={`evidence-quote ${e.stance}`} key={n}><span className="evidence-stance">{{ support: '支持', contradict: '反驳', context: '背景' }[e.stance as string]}</span>{sourceMap[e.source_id] && isDataSource(sourceMap[e.source_id]) ? <DataSnapshot source={sourceMap[e.source_id]} /> : <blockquote>{e.quote}</blockquote>}<Markdown text={e.rationale || ''} sources={report.sources || []} />{sourceMap[e.source_id] ? <SourceReference source={sourceMap[e.source_id]} scope="report" /> : <span className="citation-unresolved">来源未找到</span>}</Container>)}{!claim.evidence?.length && <Notice className="notice">暂无有效证据</Notice>}{claim.validation_warnings?.map((warning: string) => <Notice className="notice warning" key={warning}>{warning}</Notice>)}</div></Collapsible>)}</div></section>}
    {(report.positive_factors?.length > 0 || report.negative_factors?.length > 0) && <div className="factors-grid">{[{ field: 'positive_factors', title: '支持因素', icon: TrendingUp }, { field: 'negative_factors', title: '风险与反向因素', icon: TrendingDown }].map(f => <Card className="factor-box" key={f.field}><h3><f.icon size={17} />{f.title}</h3>{report[f.field]?.map((item: any, i: number) => <div className="factor" key={i}><p>{item.text}</p><div>{item.source_ids.map((id: string) => sourceMap[id] && <SourceReference key={id} source={sourceMap[id]} scope="report">来源 {report.sources.indexOf(sourceMap[id]) + 1}</SourceReference>)}{!item.source_ids.length && <small>未核实的分析推断</small>}</div></div>)}</Card>)}</div>}
    {!!report.uncertainties?.length && <section className="report-section uncertainties"><h3>仍需保留的不确定性</h3><ul>{report.uncertainties.map((text: string, i: number) => <li key={i}>{text}</li>)}</ul></section>}
    {!!report.follow_up_questions?.length && <section className="report-section"><h3>值得继续追问</h3>{report.follow_up_questions.map((q: string, i: number) => <p className="follow-up" key={i}><ArrowRight size={15} />{q}</p>)}</section>}
    {!!report.sources?.length && <section className="report-section"><h3>信息来源</h3><SourceList sources={report.sources} scope="report" /></section>}
    <Collapsible className="report-notes" title={<>报告说明</>}><p>引文已检查原文定位，语义与结论仍需审阅。研究不构成收益承诺。</p></Collapsible>
  </div>
}

export function RunDetail({ runId, onDelete }: { runId: string; onDelete: (run: Run) => void }) {
  const query = useQuery({ queryKey: ['run', runId], queryFn: () => api<Run>(`/research/runs/${runId}`), refetchInterval: q => isActive(q.state.data?.status || '') ? 3000 : false })
  const run = query.data, toast = useToast()
  const active = isActive(run?.status || '')
  useRunEvents(runId, active)
  const cancel = useMutation({ mutationFn: () => post(`/research/runs/${runId}/cancel`), onSuccess: () => query.refetch(), onError: e => toast(e.message, true) })
  if (query.isPending) return <Spinner />
  if (query.error || !run) return <ErrorState error={query.error} />
  return <div className="run-detail"><div className="run-status-bar"><Badge status={run.status} /><span>{run.stage}</span>{active && <Button className="text-button cancel" onPress={() => cancel.mutate()} disabled={cancel.isPending}><Square size={12} />取消任务</Button>}<Button className="text-button history-delete-action" onPress={() => onDelete(run)} disabled={active} title={active ? '请先停止任务后删除' : '删除研究记录'}><Trash2 size={16} />删除研究</Button></div>{run.error && <Notice className="notice warning">{run.error}</Notice>}{run.approvals?.filter(a => a.status === 'pending').map(a => <ApprovalCard key={a.id} approval={a} compact />)}{run.result?.title ? <ReportView report={run.result} /> : <div className="research-progress"><div className={`progress-emblem ${active ? 'active' : ''}`}><Search size={29} /></div><h2>{active ? '研究中' : '尚未生成报告'}</h2><p>{run.question}</p><Notice className="notice"><Clock3 size={14} />{run.stage}</Notice></div>}
    <Collapsible className="activity-log" open={!run.result} title={<>研究活动 <span>{run.events?.length || 0} 条记录</span></>}><div>{run.events?.map((event: any) => <div className="event-row" key={event.id}><span className={`event-dot ${event.type.includes('completed') ? 'done' : ''}`} /><div><strong>{event.data.stage || event.data.tool || ({ evidence_added: `收录 ${event.data.count} 条来源`, approval_required: '等待人工审批', report_completed: '结构化报告已完成', run_started: '研究开始', run_queued: '任务进入队列' } as Record<string, string>)[event.type] || event.type}</strong>{event.data.reason && <p>{event.data.reason}</p>}</div><time>{formatDate(event.created_at)}</time></div>)}</div><div className="run-budget">模型调用 {run.usage.model_calls || 0} · 工具调用 {run.usage.tool_calls || 0} · 外部请求 {run.usage.external_requests || 0} · Tokens {run.usage.total_tokens || 0}</div></Collapsible>
  </div>
}

export function Research() {
  const [params, setParams] = useSearchParams(), runId = params.get('run') || ''
  const [question, setQuestion] = useState(params.get('question') || ''), [ticker, setTicker] = useState(params.get('ticker') || '')
  const toast = useToast(), query = useQueryClient()
  const [deleting, setDeleting] = useState<Run | null>(null)
  const list = useQuery({ queryKey: ['runs'], queryFn: () => api<Run[]>('/research/runs'), refetchInterval: 12000 })
  const create = useMutation({ mutationFn: () => post('/research/runs', { question, ...(ticker ? { ticker: ticker.toUpperCase() } : {}), request_key: requestKey() }), onSuccess: r => { setParams({ run: r.id }); list.refetch() }, onError: e => toast(e.message, true) })
  const deletion = useMutation({
    mutationFn: (target: Run) => remove(`/research/runs/${target.id}`),
    onSuccess: (_, target) => {
      setParams(previous => { const next = new URLSearchParams(previous); if (next.get('run') === target.id) next.delete('run'); return next })
      setDeleting(null); query.removeQueries({ queryKey: ['run', target.id], exact: true }); query.invalidateQueries(); toast('研究记录已删除')
    },
    onError: e => toast(e.message, true),
  })
  function askDelete(target: Run) { deletion.reset(); setDeleting(target) }
  const examples = ['NVDA 最新财报中的收入增长由什么驱动？', '最近关于 AAPL 的市场观点，有哪些事实依据？', 'MSFT 的资本支出与现金流发生了什么变化？']
  return <div className="page research-page"><PageTitle title="深度研究" action={runId ? <Button className="button primary" onPress={() => setParams({})}><Plus size={16} />新研究</Button> : undefined} /><div className="research-layout"><Container className="research-history"><div className="list-label">研究记录 <span>{list.data?.length || 0}</span></div>{list.data?.map(run => <div className="history-entry" key={run.id}><Button className={`history-item ${run.id === runId ? 'selected' : ''}`} onPress={() => setParams({ run: run.id })}><div><span className="ticker-mini">{run.ticker || '综合研究'}</span><Badge status={run.status} /></div><strong>{run.title || run.question}</strong><small>{formatDate(run.created_at)}</small></Button><Button className="icon-button history-delete" aria-label={`删除研究：${run.title || run.question}`} title={isActive(run.status) ? '请先停止任务后删除' : '删除研究记录'} disabled={isActive(run.status)} onPress={() => askDelete(run)}><Trash2 size={17} /></Button></div>)}{!list.data?.length && <div className="history-empty">暂无研究记录</div>}</Container><Card className="research-main panel">{runId ? <RunDetail runId={runId} onDelete={askDelete} /> : <div className="new-research"><InitialAvatar className="new-research-icon"><Sparkles size={25} /></InitialAvatar><h2>新研究</h2><Form onSubmit={e => { e.preventDefault(); create.mutate() }}><Field label="研究问题" multiline className="field" autoFocus value={question} onChange={nextValue => setQuestion(nextValue)} minLength={2} maxLength={6000} rows={5} placeholder="输入研究问题" isRequired /><div className="research-form-bottom"><Field label="关联标的" className="ticker-input" value={ticker} onChange={nextValue => setTicker(nextValue.toUpperCase())} placeholder="NVDA · 可选" maxLength={15} /><Button className="button primary" disabled={create.isPending || question.trim().length < 2}>{create.isPending ? <LoaderCircle size={16} className="spin" /> : <Search size={16} />}开始研究</Button></div></Form><div className="suggested-questions"><span>常用问题</span>{examples.map(e => <Button key={e} onPress={() => setQuestion(e)}>{e}<ArrowUpRight size={15} /></Button>)}</div></div>}</Card></div>{deleting && <DeleteHistoryDialog kind="research" name={deleting.title || deleting.question} pending={deletion.isPending} error={deletion.error} confirm={() => deletion.mutate(deleting)} close={() => { setDeleting(null); deletion.reset() }} />}</div>
}
