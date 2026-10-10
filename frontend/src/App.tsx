import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Activity, ArrowUpRight, Bell, Command, Compass, LayoutDashboard, Menu, MessageSquare, Plus, Search, Settings2, ShieldCheck, Sparkles, X } from 'lucide-react'
import { api, ApiError } from './api'
import { Dashboard } from './pages/Dashboard'
import { Watchlist } from './pages/Watchlist'
import { Intelligence } from './pages/Intelligence'
import { Research } from './pages/Research'
import { Chat } from './pages/Chat'
import { Approvals } from './pages/Approvals'
import { Settings } from './pages/Settings'

const NAV = [
  { path: '/', label: '研究总览', sub: 'Overview', icon: LayoutDashboard },
  { path: '/watchlist', label: '关注列表', sub: 'Watchlist', icon: Activity },
  { path: '/intelligence', label: 'X 情报', sub: 'Intelligence', icon: Compass },
  { path: '/research', label: '深度研究', sub: 'Research', icon: Search },
  { path: '/chat', label: '研究对话', sub: 'Assistant', icon: MessageSquare },
  { path: '/approvals', label: '待办审批', sub: 'Approvals', icon: ShieldCheck },
]

export default function App() {
  const [menu, setMenu] = useState(false)
  const [token, setToken] = useState('')
  const location = useLocation(), navigate = useNavigate()
  const health = useQuery({ queryKey: ['health'], queryFn: () => api('/health'), refetchInterval: 15000 })
  const pending = useQuery({ queryKey: ['approvals', 'pending'], queryFn: () => api<any[]>('/approvals?status=pending'), refetchInterval: 12000 })
  const section = NAV.find(n => n.path === location.pathname)?.label || '偏好设置'
  if (health.error instanceof ApiError && health.error.status === 401) return <div className="login-page"><div className="login-card"><div className="brand-symbol">x<span>·</span></div><h1>欢迎回到研究工作台</h1><p>请输入此应用的访问令牌</p><form onSubmit={e => { e.preventDefault(); sessionStorage.setItem('app_token', token); health.refetch(); }}><input autoFocus type="password" value={token} onChange={e => setToken(e.target.value)} placeholder="APP_AUTH_TOKEN" required /><button className="button primary">进入工作台 <ArrowUpRight size={16} /></button></form></div></div>
  return <div className="app-shell">
    {menu && <div className="sidebar-scrim" onClick={() => setMenu(false)} />}
    <aside className={`sidebar ${menu ? 'open' : ''}`}>
      <NavLink to="/" className="brand"><div className="brand-symbol">x<span>·</span></div><div><strong>X Research</strong></div></NavLink>
      <div className="workspace-label"><span className="workspace-avatar">I</span><div>个人研究空间</div><span className="workspace-dot" /></div>
      
      <nav>{NAV.map(({ path, label, icon: Icon }) => <NavLink key={path} to={path} end={path === '/'} onClick={() => setMenu(false)} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><Icon size={19} strokeWidth={1.8} /><span>{label}</span>{path === '/approvals' && !!pending.data?.length && <b className="nav-count">{pending.data.length}</b>}</NavLink>)}</nav>
      <div className="sidebar-spacer" />
      
      <NavLink to="/settings" onClick={() => setMenu(false)} className={({ isActive }) => `nav-item settings-link ${isActive ? 'active' : ''}`}><Settings2 size={19} /><span>偏好设置</span></NavLink>
      <div className="sidebar-footer"><span className={`status-dot ${health.data?.worker === 'online' ? 'online' : ''}`} /><span>{health.data?.worker === 'online' ? '已连接' : '未连接'}</span><small>V1.0</small></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumbs"><button className="icon-button mobile-menu" onClick={() => setMenu(!menu)} aria-label="打开导航"><Menu size={20} /></button><strong>{section}</strong></div><div className="topbar-right"><span className="topbar-date">{new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' }).format(new Date())}</span><button className="icon-button notification" aria-label="查看待办审批" onClick={() => navigate('/approvals')}><Bell size={18} />{!!pending.data?.length && <i />}</button><div className="avatar">IL</div></div></header>
      {health.isError && <div className="global-banner">连接中断<button onClick={() => health.refetch()}>重新连接</button></div>}
      <main className={`content ${location.pathname === '/chat' ? 'chat-content' : ''}`}><Routes><Route path="/" element={<Dashboard />} /><Route path="/watchlist" element={<Watchlist />} /><Route path="/intelligence" element={<Intelligence />} /><Route path="/research" element={<Research />} /><Route path="/chat" element={<Chat />} /><Route path="/approvals" element={<Approvals />} /><Route path="/settings" element={<Settings />} /><Route path="*" element={<Dashboard />} /></Routes></main>
    </div>
  </div>
}
