import { AppLink, Card, ExternalLink, Field, Form, Notice, Button, Spinner } from './ui'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Route, Routes, useLocation } from 'react-router-dom'
import { Activity, ArrowUpRight, Compass, LayoutDashboard, MessageSquare, Search, Settings2, ShieldCheck } from 'lucide-react'
import { buttonVariants } from '@heroui/styles'
import { api, ApiError } from './api'

const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })))
const Watchlist = lazy(() => import('./pages/Watchlist').then(m => ({ default: m.Watchlist })))
const Intelligence = lazy(() => import('./pages/Intelligence').then(m => ({ default: m.Intelligence })))
const Research = lazy(() => import('./pages/Research').then(m => ({ default: m.Research })))
const Chat = lazy(() => import('./pages/Chat').then(m => ({ default: m.Chat })))
const Approvals = lazy(() => import('./pages/Approvals').then(m => ({ default: m.Approvals })))
const Settings = lazy(() => import('./pages/Settings').then(m => ({ default: m.Settings })))

const NAV = [
  { path: '/', label: '研究总览', icon: LayoutDashboard },
  { path: '/watchlist', label: '关注列表', icon: Activity },
  { path: '/intelligence', label: 'X 情报', icon: Compass },
  { path: '/research', label: '深度研究', icon: Search },
  { path: '/chat', label: '研究对话', icon: MessageSquare },
  { path: '/approvals', label: '待办审批', icon: ShieldCheck },
]
// HeroUI's public variant API keeps real anchors and React Router navigation semantics.
const pillClasses = buttonVariants({ variant: 'secondary' })

export default function App() {
  const [token, setToken] = useState('')
  const location = useLocation(), navigation = useRef<HTMLElement>(null)
  const health = useQuery({ queryKey: ['health'], queryFn: () => api('/health'), refetchInterval: 15000 })
  const pending = useQuery({ queryKey: ['approvals', 'pending'], queryFn: () => api<any[]>('/approvals?status=pending'), refetchInterval: 12000 })
  const section = NAV.find(n => n.path === location.pathname)?.label || '偏好设置'
  useEffect(() => {
    document.title = `${section} · X Research`
    // On small screens the pills scroll horizontally; keep the active destination in view.
    navigation.current?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: 'nearest', inline: 'center' })
  }, [section])

  if (health.error instanceof ApiError && health.error.status === 401) return <div className="login-page">
    <div className="login-art" aria-hidden="true"><div className="brand-symbol">x<span>·</span></div><h2>Research.<br />With perspective.</h2><div className="login-orbit" /></div>
    <Card className="login-card"><span className="eyebrow">X RESEARCH</span><h1>进入研究工作台</h1><p>使用共享访问口令继续研究</p>
      <Form onSubmit={e => { e.preventDefault(); sessionStorage.setItem('app_token', token); health.refetch() }}>
        <Field label="访问口令" className="field" autoFocus type="password" value={token} onChange={nextValue => setToken(nextValue)} placeholder="输入访问口令" autoComplete="current-password" isRequired />
        <Button className="button primary full">进入工作台 <ArrowUpRight size={18} /></Button>
      </Form></Card>
  </div>

  return <div className="app-shell">
    <ExternalLink className="skip-link" href="#main-content">跳至主要内容</ExternalLink>
    <header className="floating-navigation" aria-label="工作台导航">
      <nav className="navigation-pills" aria-label="主导航" ref={navigation}>{NAV.map(({ path, label, icon: Icon }) =>
        <AppLink key={path} to={path} aria-current={location.pathname === path ? 'page' : undefined} className={`${pillClasses} navigation-pill ${location.pathname === path ? 'active' : ''}`}>
          <Icon size={18} strokeWidth={1.8} /><span>{label}</span>{path === '/approvals' && !!pending.data?.length && <span className="nav-count">{pending.data.length}</span>}
        </AppLink>)}</nav>
      <AppLink to="/settings" aria-label="偏好设置" aria-current={location.pathname === '/settings' ? 'page' : undefined} className={`${pillClasses} navigation-pill settings-pill ${location.pathname === '/settings' ? 'active' : ''}`}>
        <Settings2 size={18} /><span className="settings-pill-label">偏好设置</span>
      </AppLink>
    </header>
    <main id="main-content" className={`content ${location.pathname === '/chat' ? 'chat-content' : ''}`}>
      {health.isError && <Notice className="global-banner notice error">连接中断<Button onPress={() => health.refetch()}>重新连接</Button></Notice>}
      <Suspense fallback={<Spinner />}><Routes><Route path="/" element={<Dashboard />} /><Route path="/watchlist" element={<Watchlist />} /><Route path="/intelligence" element={<Intelligence />} /><Route path="/research" element={<Research />} /><Route path="/chat" element={<Chat />} /><Route path="/approvals" element={<Approvals />} /><Route path="/settings" element={<Settings />} /><Route path="*" element={<Dashboard />} /></Routes></Suspense>
    </main>
  </div>
}
