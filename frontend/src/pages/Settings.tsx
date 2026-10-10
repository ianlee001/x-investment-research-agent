import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Save } from 'lucide-react'
import { api } from '../api'
import { ErrorState, PageTitle, Panel, Spinner, useToast } from '../ui'

const PROVIDERS: Record<string, string> = {
  dashscope: 'DashScope / Qwen', tavily: 'Tavily', x: 'X API', massive: 'Massive', sec: 'SEC EDGAR',
}

export function Settings() {
  const query = useQuery({ queryKey: ['settings'], queryFn: () => api('/settings') }), toast = useToast()
  const [prefs, setPrefs] = useState<any>(null)
  useEffect(() => { if (query.data && !prefs) setPrefs(query.data.preferences) }, [query.data, prefs])
  const save = useMutation({
    mutationFn: () => api('/settings', { method: 'PUT', body: JSON.stringify(prefs) }),
    onSuccess: () => { query.refetch(); toast('设置已保存') }, onError: e => toast(e.message, true),
  })
  return <div className="page settings-page">
    <PageTitle title="偏好设置" action={<button className="button primary" disabled={save.isPending || !prefs}
      onClick={() => save.mutate()}><Save size={18} />保存设置</button>} />
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
        <Panel title="自动任务">
          <div className="setting-row"><strong>同步 X 账号</strong>
            <button role="switch" aria-checked={prefs.sync_enabled} aria-label="自动同步 X 账号"
              className={`toggle ${prefs.sync_enabled ? 'on' : ''}`}
              onClick={() => setPrefs({ ...prefs, sync_enabled: !prefs.sync_enabled })}><span /></button>
          </div>
          <label className="field inline-field">同步间隔<select value={prefs.sync_interval_minutes}
            onChange={e => setPrefs({ ...prefs, sync_interval_minutes: Number(e.target.value) })}>
            {[30, 60, 120, 240, 720, 1440].map(n => <option key={n} value={n}>{n} 分钟</option>)}
          </select></label>
          <div className="setting-row"><strong>每日简报</strong>
            <button role="switch" aria-checked={prefs.daily_brief_enabled} aria-label="每日研究简报"
              className={`toggle ${prefs.daily_brief_enabled ? 'on' : ''}`}
              onClick={() => setPrefs({ ...prefs, daily_brief_enabled: !prefs.daily_brief_enabled })}><span /></button>
          </div>
          <label className="field inline-field">生成时间<select value={prefs.daily_brief_hour}
            onChange={e => setPrefs({ ...prefs, daily_brief_hour: Number(e.target.value) })}>
            {Array.from({ length: 24 }, (_, i) => <option key={i} value={i}>{String(i).padStart(2, '0')}:00</option>)}
          </select></label>
          <label className="field inline-field">时区<select value={prefs.timezone}
            onChange={e => setPrefs({ ...prefs, timezone: e.target.value })}>
            <option>Asia/Shanghai</option><option>America/New_York</option><option>UTC</option>
          </select></label>
          <div className="setting-row"><div><strong>核查关注标的相关帖子</strong><p>开启后使用外部 API 额度</p></div>
            <button role="switch" aria-checked={prefs.auto_research_enabled} aria-label="自动核查相关帖子"
              className={`toggle ${prefs.auto_research_enabled ? 'on' : ''}`}
              onClick={() => setPrefs({ ...prefs, auto_research_enabled: !prefs.auto_research_enabled })}><span /></button>
          </div>
          <label className="field inline-field">每日核查上限<input type="number" min="0" max="10"
            value={prefs.auto_research_max_per_day}
            onChange={e => setPrefs({ ...prefs, auto_research_max_per_day: Number(e.target.value) })} /></label>
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
