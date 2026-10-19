import { NumberInput, SelectInput, Button, ErrorState, PageTitle, Panel, Spinner, useToast } from '../ui'
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Save } from 'lucide-react'
import { Switch } from '@heroui/react'
import { api } from '../api'

const PROVIDERS: Record<string, string> = {
  dashscope: 'DashScope / Qwen', tavily: 'Tavily', x: 'X API', massive: 'Massive', sec: 'SEC EDGAR',
}
type Preferences = {
  sync_enabled: boolean; sync_interval_minutes: number; daily_brief_enabled: boolean;
  daily_brief_hour: number; timezone: string; auto_research_enabled: boolean; auto_research_max_per_day: number
}

export function Settings() {
  const query = useQuery({ queryKey: ['settings'], queryFn: () => api('/settings') }), toast = useToast(), client = useQueryClient()
  const [prefs, setPrefs] = useState<Preferences | null>(null)
  useEffect(() => { if (query.data && !prefs) setPrefs(query.data.preferences) }, [query.data, prefs])
  const save = useMutation({
    mutationFn: (next: Preferences) => api<Preferences>('/settings', { method: 'PUT', body: JSON.stringify(next) }),
    onSuccess: saved => {
      setPrefs(saved)
      client.setQueryData(['settings'], (previous: any) => ({ ...previous, preferences: saved }))
      toast('设置已保存')
    }, onError: e => toast(`保存失败：${e.message}`, true),
  })
  function toggle(key: 'sync_enabled' | 'daily_brief_enabled' | 'auto_research_enabled', value: boolean) {
    if (!prefs || save.isPending) return
    const previous = prefs, next = { ...prefs, [key]: value }
    setPrefs(next)
    save.mutate(next, { onError: () => setPrefs(previous) })
  }
  return <div className="page settings-page">
    <PageTitle title="偏好设置" action={<Button className="button primary" disabled={save.isPending || !prefs}
      onPress={() => prefs && save.mutate(prefs)}><Save size={18} />{save.isPending ? '保存中…' : '保存设置'}</Button>} />
    {save.isError && <ErrorState error={save.error} />}
    {query.isPending ? <Spinner /> : query.error ? <ErrorState error={query.error} /> : <>
      <Panel title="数据连接"><div className="connection-list">
        {Object.entries(query.data.providers).map(([key, configured]) => <div className="connection-row" key={key}>
          <div><strong>{PROVIDERS[key]}</strong>{key === 'dashscope' && <small>{query.data.llm_model}</small>}</div>
          <span className={`connection-state ${configured ? 'configured' : ''}`}><span className="tiny-dot" />
            {query.data.provider_health[key]?.ok ? '实测可用' : configured ? '已配置' : '待配置'}
          </span>
        </div>)}
      </div></Panel>
      {prefs && <div className="settings-grid">
        <Panel title="自动任务" meta={<span className="settings-save-state" aria-live="polite">{save.isPending ? '正在保存…' : '开关自动保存'}</span>}>
          <div className="setting-row"><strong>同步 X 账号</strong>
            <Switch aria-label="自动同步 X 账号" isDisabled={save.isPending} isSelected={prefs.sync_enabled} onChange={value => toggle('sync_enabled', value)}><Switch.Content><Switch.Control><Switch.Thumb /></Switch.Control></Switch.Content></Switch>
          </div>
          <SelectInput label="同步间隔" className="field inline-field" visibleLabel disabled={save.isPending} value={prefs.sync_interval_minutes} onChange={nextValue => setPrefs({ ...prefs, sync_interval_minutes: Number(nextValue) })} options={[...[30, 60, 120, 240, 720, 1440].map((n) => ({ value: String(n), label: [n, " 分钟"].join('') }))]} />
          <div className="setting-row"><strong>每日简报</strong>
            <Switch aria-label="每日研究简报" isDisabled={save.isPending} isSelected={prefs.daily_brief_enabled} onChange={value => toggle('daily_brief_enabled', value)}><Switch.Content><Switch.Control><Switch.Thumb /></Switch.Control></Switch.Content></Switch>
          </div>
          <SelectInput label="生成时间" className="field inline-field" visibleLabel disabled={save.isPending} value={prefs.daily_brief_hour} onChange={nextValue => setPrefs({ ...prefs, daily_brief_hour: Number(nextValue) })} options={[...Array.from({ length: 24 }, (_, i) => ({ value: String(i), label: [String(i).padStart(2, '0'), ":00"].join('') }))]} />
          <SelectInput label="时区" className="field inline-field" visibleLabel disabled={save.isPending} value={prefs.timezone} onChange={nextValue => setPrefs({ ...prefs, timezone: nextValue })} options={[({ value: String("Asia/Shanghai"), label: String("Asia/Shanghai") }), ({ value: String("America/New_York"), label: String("America/New_York") }), ({ value: String("UTC"), label: String("UTC") })]} />
          <div className="setting-row"><div><strong>核查关注标的相关帖子</strong><p>开启后使用外部 API 额度</p></div>
            <Switch aria-label="自动核查相关帖子" isDisabled={save.isPending} isSelected={prefs.auto_research_enabled} onChange={value => toggle('auto_research_enabled', value)}><Switch.Content><Switch.Control><Switch.Thumb /></Switch.Control></Switch.Content></Switch>
          </div>
          <NumberInput label="每日核查上限" disabled={save.isPending} min={Number("0")} max={Number("10")} value={prefs.auto_research_max_per_day} onChange={nextValue => setPrefs({ ...prefs, auto_research_max_per_day: Number(nextValue) })} />
        </Panel>
        <Panel title="运行限额"><dl className="limits-list">
          {Object.entries(query.data.limits).map(([key, value]) => <div key={key}>
            <dt>{{ model_calls: '模型调用', tool_calls: '工具调用', external_requests: '外部请求',
              total_tokens: '总 Token', timeout_seconds: '单次执行时限（秒）' }[key]}</dt><dd>{String(value)}</dd>
          </div>)}
        </dl></Panel>
      </div>}
    </>}
  </div>
}
