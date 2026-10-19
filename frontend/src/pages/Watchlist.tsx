import { InitialAvatar, Card, Container, Field, Form, Notice, AppLink as Link, Button, Badge, Empty, ErrorState, Modal, PageTitle, Panel, Spinner, useToast } from '../ui'

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Activity, ArrowUpRight, ChevronRight, Plus, Trash2 } from 'lucide-react'
import { api, formatDate, number, post, remove } from '../api'

import { AreaChart } from '../components/tremor/AreaChart'

function PriceChart({ bars }: { bars: any[] }) {
  if (!bars.length) return null
  const data = bars.map(b => ({ date: new Date(b.t).toISOString().slice(0, 10), 收盘价: b.c }))
  return <div className="price-chart" role="group" aria-label={`最近${bars.length}个交易日复权收盘价走势`}>
    <div className="chart-heading"><strong>价格走势</strong><span>日线 · 复权 · USD</span></div>
    <AreaChart className="market-area-chart h-64" data={data} index="date" categories={['收盘价']} colors={['blue']}
      autoMinValue showLegend={false} yAxisWidth={64} valueFormatter={value => `$${number(value)}`} />
  </div>
}

function StockDetail({ ticker }: { ticker: string }) {
  const detail = useQuery({ queryKey: ['watch', ticker], queryFn: () => api(`/watchlist/${ticker}`) })
  const quote = useQuery({ queryKey: ['quote', ticker], queryFn: () => api(`/market/${ticker}/quote`), staleTime: 600000 })
  const history = useQuery({ queryKey: ['history', ticker], queryFn: () => api(`/market/${ticker}/history`), staleTime: 600000 })
  const profile = useQuery({ queryKey: ['profile', ticker], queryFn: () => api(`/market/${ticker}/profile`), staleTime: 3600000 })
  const price = quote.data?.data, company = profile.data?.data
  return <Panel className="stock-detail"><div className="stock-detail-heading"><InitialAvatar className="company-avatar large">{ticker.slice(0, 1)}</InitialAvatar><div><span className="ticker-overline">{ticker} <span>{company?.primary_exchange || '美股'}</span></span><h2>{company?.name || detail.data?.company_name || ticker}</h2></div><Link className="button secondary small" to={`/research?ticker=${ticker}`}>研究此标的 <ArrowUpRight size={15} /></Link></div><div className="price-block"><span className="data-label">上一交易日收盘价</span><strong>{quote.isPending ? '读取中…' : price ? `$${number(price.close)}` : '暂不可用'}</strong><div className="price-subline">{price && <span className={price.intraday_change_percent >= 0 ? 'positive' : 'negative'}>{price.intraday_change_percent >= 0 ? '+' : ''}{number(price.intraday_change_percent)}% <small>相对当日开盘</small></span>}<span>{price?.as_of ? `${formatDate(price.as_of)} · 非实时` : quote.data?.reason || '等待行情数据'}</span></div></div>{history.isPending ? <Spinner /> : history.data?.available ? <PriceChart bars={history.data.data.bars} /> : <Notice className="notice">历史行情暂不可用：{history.data?.reason || '连接失败'}</Notice>}<div className="stock-metrics"><div><span>成交量</span><strong>{number(price?.volume, 0)}</strong></div><div><span>当日最高</span><strong>{number(price?.high)}</strong></div><div><span>当日最低</span><strong>{number(price?.low)}</strong></div><div><span>市值</span><strong>{company?.market_cap ? `$${number(company.market_cap / 1e9)}B` : '未提供'}</strong></div></div><div className="stock-thesis"><div className="panel-heading"><h3>研究观点</h3><Link className="subtle-link" to={`/chat?prompt=${encodeURIComponent(`请帮我为 ${ticker} 保存研究观点：`)}`}>在对话中更新 <ArrowUpRight size={13} /></Link></div><p>{detail.data?.thesis || '暂无研究观点'}</p></div><div className="stock-reports"><h3>相关研究</h3>{detail.data?.reports?.length ? detail.data.reports.map((run: any) => <Link key={run.id} to={`/research?run=${run.id}`} className="stock-report-row"><span>{run.title}</span><Badge status={run.status} /><ChevronRight size={15} /></Link>) : <p className="muted">暂无相关研究</p>}</div><div className="data-credit">数据来源：Massive</div></Panel>
}

export function Watchlist() {
  const [selected, setSelected] = useState(''), [adding, setAdding] = useState(false), [ticker, setTicker] = useState(''), [notes, setNotes] = useState(''), [deleting, setDeleting] = useState('')
  const query = useQueryClient(), toast = useToast()
  const list = useQuery({ queryKey: ['watchlist'], queryFn: () => api<any[]>('/watchlist') })
  const add = useMutation({ mutationFn: () => post('/watchlist', { ticker, notes }), onSuccess: r => { setSelected(r.ticker); setAdding(false); setTicker(''); setNotes(''); query.invalidateQueries({ queryKey: ['watchlist'] }); toast('已添加关注标的') }, onError: e => toast(e.message, true) })
  const del = useMutation({ mutationFn: () => remove(`/watchlist/${deleting}`), onSuccess: () => { if (selected === deleting) setSelected(''); setDeleting(''); query.invalidateQueries({ queryKey: ['watchlist'] }); toast('已移出关注列表') }, onError: e => toast(e.message, true) })
  const current = selected && list.data?.some(i => i.ticker === selected) ? selected : list.data?.[0]?.ticker
  return <div className="page"><PageTitle title="关注列表" action={<Button className="button primary" onPress={() => setAdding(true)}><Plus size={17} />添加标的</Button>} />{list.isPending ? <Spinner /> : list.error ? <ErrorState error={list.error} /> : list.data?.length ? <div className="watch-layout"><Container className="watch-sidebar"><div className="list-label">全部标的 <span>{list.data.length}</span></div>{list.data.map(item => <div className={`watch-item ${item.ticker === current ? 'selected' : ''}`} key={item.ticker}><Button onPress={() => setSelected(item.ticker)}><InitialAvatar className="company-avatar">{item.ticker.slice(0, 1)}</InitialAvatar><span><strong>{item.ticker}</strong><small>{item.company_name || item.notes || '美国股票'}</small></span></Button><Button className="icon-button" onPress={() => setDeleting(item.ticker)} aria-label={`移除 ${item.ticker}`}><Trash2 size={14} /></Button></div>)}</Container>{current && <StockDetail key={current} ticker={current} />}</div> : <Card className="panel"><Empty icon={<Activity size={30} />} title="暂无关注标的" action={<Button className="button primary" onPress={() => setAdding(true)}><Plus size={16} />添加第一个标的</Button>} /></Card>}
    {adding && <Modal title="添加关注标的" close={() => setAdding(false)}><Form onSubmit={e => { e.preventDefault(); add.mutate() }}><Field label="股票代码" className="field" autoFocus value={ticker} onChange={nextValue => setTicker(nextValue.toUpperCase())} placeholder="例如 NVDA、AAPL、MSFT" pattern="[A-Z][A-Z0-9.\-]{0,14}" isRequired /><Field label="关注原因（可选）" multiline className="field" value={notes} onChange={nextValue => setNotes(nextValue)} rows={3} placeholder="添加备注" /><Button className="button primary full" disabled={add.isPending}>添加到关注列表</Button></Form></Modal>}
    {deleting && <Modal title={`移除 ${deleting}？`} close={() => setDeleting('')}><p className="form-note">研究报告将保留。</p><Button className="button danger full" disabled={del.isPending} onPress={() => del.mutate()}>确认移除</Button></Modal>}
  </div>
}
