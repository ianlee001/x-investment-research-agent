import { useMutation, useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, ArrowUpRight, BookOpen, Compass, FileText, Plus, ShieldCheck } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api, formatDate, post, type Run } from '../api'
import { Badge, Empty, ErrorState, PageTitle, Panel, Spinner, useToast } from '../ui'

const STATS = [
  { key: 'watchlist', name: '关注标的', icon: Activity, to: '/watchlist' },
  { key: 'posts', name: 'X 情报', icon: Compass, to: '/intelligence' },
  { key: 'reports', name: '研究报告', icon: FileText, to: '/research' },
  { key: 'pending_approvals', name: '待办审批', icon: ShieldCheck, to: '/approvals' },
]

export function Dashboard() {
  const navigate = useNavigate(), toast = useToast()
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['dashboard'], queryFn: () => api('/dashboard'), refetchInterval: 15000,
  })
  const brief = useMutation({
    mutationFn: () => post('/daily-brief'),
    onSuccess: r => navigate(`/research?run=${r.id}`), onError: e => toast(e.message, true),
  })
  const counts = data?.counts || {}
  return <div className="page dashboard-page">
    <PageTitle title="研究总览" action={<Link className="button primary" to="/research"><Plus size={18} />新研究</Link>} />
    <div className="stat-grid">{STATS.map(s => <Link to={s.to} className="stat-card" key={s.key}>
      <div className="stat-top"><span>{s.name}</span><s.icon size={20} /></div>
      <strong>{isPending ? '—' : counts[s.key] ?? 0}<ArrowUpRight size={18} /></strong>
    </Link>)}</div>
    {error && <ErrorState error={error} retry={() => refetch()} />}
    <div className="dashboard-grid">
      <Panel title="最近研究" meta={<Link className="subtle-link" to="/research">查看全部 <ArrowRight size={16} /></Link>}>
        {isPending ? <Spinner /> : data?.recent_runs?.length ? <div className="run-list">
          {data.recent_runs.map((run: Run) => <Link className="run-row"
            to={run.kind === 'chat' ? `/chat?thread=${run.thread_id}` : `/research?run=${run.id}`} key={run.id}>
            <div className="row-icon"><FileText size={20} /></div>
            <div className="run-row-copy"><strong>{run.title}</strong>
              <span>{run.ticker && <b>{run.ticker}</b>}{formatDate(run.created_at)}</span>
            </div><Badge status={run.status} /><ArrowUpRight size={18} className="muted" />
          </Link>)}
        </div> : <Empty icon={<BookOpen size={28} />} title="暂无研究记录"
          action={<Link to="/research" className="button secondary">新研究</Link>} />}
      </Panel>
      <Panel title="每日简报" className="brief-panel">
        {data?.daily_brief ? <>
          <h3>{data.daily_brief.result?.title}</h3>
          <p className="line-clamp-4">{data.daily_brief.result?.summary}</p>
          <Link className="text-button" to={`/research?run=${data.daily_brief.id}`}>阅读全文 <ArrowRight size={16} /></Link>
        </> : <div className="brief-empty"><FileText size={32} /><p>暂无今日简报</p>
          <button className="button secondary" disabled={brief.isPending || !counts.watchlist}
            onClick={() => brief.mutate()}>{brief.isPending ? '正在创建…' : '生成简报'}</button>
          {!counts.watchlist && <Link className="text-button" to="/watchlist">添加关注标的 <ArrowRight size={16} /></Link>}
        </div>}
      </Panel>
    </div>
  </div>
}
