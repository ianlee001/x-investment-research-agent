import { Card, Container, Form, SearchInput, AppLink as Link, Button, Badge, Empty, ErrorState, Panel, Spinner, useToast } from '../ui'
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, ArrowUpRight, BookOpen, Compass, FileText, MessageSquare, Plus, ShieldCheck, Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { api, formatDate, post, type Run } from '../api'

const STATS = [
  { key: 'watchlist', name: '关注标的', icon: Activity, to: '/watchlist', tone: 'indigo' },
  { key: 'posts', name: 'X 情报', icon: Compass, to: '/intelligence', tone: 'cyan' },
  { key: 'reports', name: '研究报告', icon: FileText, to: '/research', tone: 'violet' },
  { key: 'pending_approvals', name: '待办审批', icon: ShieldCheck, to: '/approvals', tone: 'amber' },
]

export function Dashboard() {
  const navigate = useNavigate(), toast = useToast(), [question, setQuestion] = useState('')
  const { data, isPending, error, refetch } = useQuery({ queryKey: ['dashboard'], queryFn: () => api('/dashboard'), refetchInterval: 15000 })
  const brief = useMutation({ mutationFn: () => post('/daily-brief'), onSuccess: r => navigate(`/research?run=${r.id}`), onError: e => toast(e.message, true) })
  const counts = data?.counts || {}
  return <div className="page dashboard-page">
    <div className="overview-heading"><div><span className="eyebrow">X RESEARCH</span><h1>研究总览</h1></div><Button className="button primary" onPress={() => navigate('/chat')}><Plus size={17} />发起研究</Button></div>
    <Container className="research-launchpad"><div className="launchpad-copy"><span className="launchpad-icon"><Sparkles size={22} /></span><h2>今天，研究什么？</h2></div>
      <Form className="overview-search" onSubmit={event => { event.preventDefault(); if (question.trim()) navigate(`/research?question=${encodeURIComponent(question.trim())}`) }}><SearchInput label={"快速研究问题"} placeholder="输入标的、市场事件或想核实的观点" value={question} onChange={nextValue => setQuestion(nextValue)} /><Button className="button primary" disabled={!question.trim()}>开始研究<ArrowUpRight size={17} /></Button></Form>
      <div className="quick-topics">{['NVDA 最新财报中的增长驱动', '半导体板块近期的风险因素', '我的关注标的有哪些新动态？'].map(topic => <Link to={`/research?question=${encodeURIComponent(topic)}`} key={topic}>{topic}<ArrowUpRight size={14} /></Link>)}</div>
    </Container>
    <div className="stat-grid">{STATS.map(s => <Card className="stat-container" key={s.key}><Link to={s.to} className={`stat-card ${s.tone}`}>
      <div className="stat-top"><span className="stat-icon"><s.icon size={20} /></span><ArrowUpRight size={17} /></div><strong>{isPending ? '—' : counts[s.key] ?? 0}</strong><span className="stat-label">{s.name}</span>
    </Link></Card>)}</div>
    {!!error && <ErrorState error={error} retry={() => refetch()} />}
    <div className="dashboard-grid"><Panel title="最近研究" meta={<Link className="subtle-link" to="/research">全部研究 <ArrowRight size={16} /></Link>}>
      {isPending ? <Spinner /> : data?.recent_runs?.length ? <div className="run-list">{data.recent_runs.map((run: Run) => <Link className="run-row" to={run.kind === 'chat' ? `/chat?thread=${run.thread_id}` : `/research?run=${run.id}`} key={run.id}>
        <div className={`row-icon ${run.kind === 'chat' ? 'chat' : ''}`}>{run.kind === 'chat' ? <MessageSquare size={19} /> : <FileText size={19} />}</div><div className="run-row-copy"><strong>{run.title || run.question}</strong><span>{run.ticker && <b>{run.ticker}</b>}{formatDate(run.created_at)}</span></div><Badge status={run.status} /><ArrowUpRight size={17} className="muted" />
      </Link>)}</div> : <Empty icon={<BookOpen size={28} />} title="暂无研究记录" action={<Link to="/research" className="button secondary">发起第一份研究<ArrowUpRight size={16} /></Link>} />}
    </Panel><div className="dashboard-rail"><Panel title="每日简报" className="brief-panel" meta={<span className="brief-symbol"><FileText size={18} /></span>}>
      {data?.daily_brief ? <div className="brief-body"><span className="eyebrow">DAILY BRIEF</span><h3>{data.daily_brief.result?.title}</h3><p className="line-clamp-4">{data.daily_brief.result?.summary}</p><Link className="text-button" to={`/research?run=${data.daily_brief.id}`}>阅读简报<ArrowRight size={17} /></Link></div> : <div className="brief-empty"><span className="eyebrow">DAILY BRIEF</span><h3>把关注，整理成洞察。</h3><p>暂无今日简报</p><Button className="button secondary" disabled={brief.isPending || !counts.watchlist} onPress={() => brief.mutate()}>{brief.isPending ? '正在创建…' : '生成简报'}<ArrowRight size={17} /></Button>{!counts.watchlist && <Link className="text-button" to="/watchlist">添加关注标的<ArrowUpRight size={16} /></Link>}</div>}
    </Panel><Card className="shortcut-container"><Link className="intelligence-shortcut" to="/intelligence"><span className="row-icon"><Compass size={22} /></span><div><strong>捕捉市场观点</strong><span>查看 X 情报</span></div><ArrowUpRight size={20} /></Link></Card></div></div>
  </div>
}
