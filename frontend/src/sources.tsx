import { Link as HeroLink, Card, Surface as Container } from '@heroui/react'
import { Collapsible } from './components/Collapsible'

import { ArrowUpRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { formatDate, number } from './api'

export type ResearchSource = {
  id: string; title: string; url: string; source_type?: string; provider?: string;
  excerpt?: string; retrieved_at?: string; published_at?: string; metadata_json?: Record<string, unknown>;
}

export function publicSourceUrl(value?: string): string | undefined {
  try {
    const url = new URL(value || '')
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return
    // Provider endpoints are provenance, not publicly readable articles. Never append credentials.
    if (['api.massive.com', 'api.polygon.io', 'data.sec.gov'].includes(url.hostname)) return
    if ([...url.searchParams.keys()].some(key => /^(api[_-]?key|token|access_token|authorization)$/i.test(key))) return
    return url.href
  } catch { return }
}

export function sourceData(source: ResearchSource): unknown | undefined {
  const text = source.excerpt?.trim()
  if (!text || !['{', '['].includes(text[0])) return
  try {
    const value: unknown = JSON.parse(text)
    if (value !== null && typeof value === 'object') return value
  } catch { /* Truncated snapshots are still identified by provider/type below. */ }
}

export function isDataSource(source: ResearchSource): boolean {
  return source.source_type === 'market' || sourceData(source) !== undefined ||
    /https?:\/\/(?:api\.(?:massive\.com|polygon\.io)|data\.sec\.gov)\//i.test(source.url)
}

export function articleUrl(source: ResearchSource): string | undefined {
  return isDataSource(source) ? undefined : publicSourceUrl(source.url)
}

export function sourceAnchor(scope: string, id: string): string { return `${scope}-source-${id}` }

export function citedSources(text: string, sources: ResearchSource[]): ResearchSource[] {
  return sources.filter(source => text.includes(source.id) || (!!source.url && text.includes(source.url)))
}

const fieldNames: Record<string, string> = {
  ticker: '股票代码', close: '收盘价', open: '开盘价', high: '最高价', low: '最低价', volume: '成交量（股）',
  currency: '币种', currency_name: '币种', as_of: '数据时间', session_date: '交易日期', price_type: '价格口径',
  adjusted: '价格复权', is_realtime: '实时数据', intraday_change_percent: '当日开盘至收盘变化',
  change_basis: '比较基准', start: '开始日期', end: '结束日期', timespan: '周期', bars: '日线记录',
  total_bars: '区间记录数', period_return_percent: '区间首末收盘变化', name: '公司名称', company: '公司',
  primary_exchange: '交易所', market_cap: '市值（USD）', description: '说明', homepage_url: '公司网站',
  total_employees: '员工数', list_date: '上市日期', last_updated_utc: '更新时间', market: '市场',
  locale: '地区', type: '证券类型', active: '是否活跃', cik: 'SEC 公司编号', taxonomy: '会计分类标准',
  tag: '财务指标', label: '指标名称', unit: '单位', facts: '财务记录', filed: '提交日期',
  form: '申报类型', report_date: '报告日期', accession: '申报编号', accn: '申报编号',
  primary_document: '申报文件', url: '申报原文', val: '数值', fy: '财年', fp: '财务期间',
  frame: '报告期间', scope: '数据范围', as_of_filter: '截止日期',
  t: '时间（UTC）', o: '开盘价', h: '最高价', l: '最低价', c: '收盘价', v: '成交量（股）',
  vw: '成交量加权均价', n: '成交笔数',
}
const valueNames: Record<string, string> = {
  previous_session_close: '上一交易日收盘', close_vs_same_session_open: '同一交易日收盘价与开盘价比较',
  day: '日', standard_taxonomy_entity_wide: '公司整体标准会计口径',
  recent_filings_not_full_archive: '近期申报记录', stocks: '股票',
}

function DataValue({ value, field = '', depth = 0 }: { value: unknown; field?: string; depth?: number }) {
  if (value == null) return <span>未提供</span>
  if (typeof value === 'boolean') return <span>{value ? '是' : '否'}</span>
  if (typeof value === 'number') {
    const date = field === 't' ? new Date(value) : undefined
    const display = date && Number.isFinite(date.getTime()) ? date.toISOString().replace('T', ' ').replace('.000Z', ' UTC') : number(value, 6)
    return <span>{display}{field.endsWith('_percent') ? '%' : ''}</span>
  }
  if (typeof value === 'string') {
    const href = ['url', 'homepage_url'].includes(field) ? publicSourceUrl(value) : undefined
    return href ? <HeroLink href={href} target="_blank" rel="noreferrer noopener">查看原文<ArrowUpRight size={13} /></HeroLink> : <span>{valueNames[value] || value}</span>
  }
  if (depth >= 5) return <span>更多嵌套记录</span>
  if (Array.isArray(value)) return <div className="snapshot-records">{value.slice(0, 30).map((item, i) =>
    <Card className="snapshot-record" key={i}><DataValue value={item} depth={depth + 1} /></Card>)}
    {value.length > 30 && <p>显示前 30 条，共 {value.length} 条</p>}{!value.length && <span>暂无记录</span>}</div>
  return <dl className="snapshot-fields">{Object.entries(value as Record<string, unknown>).map(([key, item]) =>
    <div key={key}><dt>{fieldNames[key] || key}</dt><dd><DataValue value={item} field={key} depth={depth + 1} /></dd></div>)}</dl>
}

export function DataSnapshot({ source }: { source: ResearchSource }) {
  const data = sourceData(source)
  return <Container className="data-snapshot">{data === undefined ?
    <p>已保存该来源，但数据快照不完整，暂时无法展开字段。</p> : <DataValue value={data} />}</Container>
}

export function SourceReference({ source, scope, children }: { source: ResearchSource; scope: string; children?: ReactNode }) {
  const href = articleUrl(source)
  return <HeroLink className="citation-link" href={href || `#${sourceAnchor(scope, source.id)}`}
    target={href ? '_blank' : undefined} rel={href ? 'noreferrer noopener' : undefined}>
    {children || source.title}{href && <ArrowUpRight size={13} />}</HeroLink>
}

export function SourceLink({ source, index }: { source: ResearchSource; index?: number }) {
  const href = articleUrl(source), data = isDataSource(source)
  let host = ''
  try { host = new URL(source.url).hostname } catch { /* No fabricated replacement URL. */ }
  const body = <><span className="source-number">{index != null ? String(index + 1).padStart(2, '0') : '·'}</span>
    <div><strong>{source.title}</strong><span>{data ? '数据快照' : host || '来源记录'}</span></div>{href && <ArrowUpRight size={16} />}</>
  return href ? <HeroLink className="source-link" href={href} target="_blank" rel="noreferrer noopener">{body}</HeroLink> : <div className="source-link">{body}</div>
}

export function SourceList({ sources, scope, compact = false }: { sources: ResearchSource[]; scope: string; compact?: boolean }) {
  if (!sources.length) return null
  return <div className={`source-list ${compact ? 'message-sources' : ''}`}>{sources.map((source, i) =>
    <Card className="source-entry" id={sourceAnchor(scope, source.id)} key={source.id}>
      <SourceLink source={source} index={i} />
      <Collapsible className="source-details" open={compact && isDataSource(source)} title={<>{isDataSource(source) ? '查看数据' : '查看摘录'}</>}><p>{source.retrieved_at && <>获取：{formatDate(source.retrieved_at)} · </>}{source.source_type === 'market' ? '数据日期' : '发布'}：{source.published_at || '来源未提供'}</p>{isDataSource(source) ? <DataSnapshot source={source} /> : <blockquote className="source-excerpt">{source.excerpt}</blockquote>}</Collapsible>
    </Card>)}</div>
}
