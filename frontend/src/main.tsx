import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { ToastProvider } from './ui'
import './styles.css'
import './readability.css'

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 10000, retry: 1, refetchOnWindowFocus: true } } })
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><ToastProvider><App /></ToastProvider></BrowserRouter></QueryClientProvider></React.StrictMode>)
