import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { headers } from './api'

export function useRunEvents(runId?: string, active = true) {
  const [liveText, setLiveText] = useState('')
  const [connection, setConnection] = useState('connecting')
  const query = useQueryClient()
  const cursor = useRef(0)
  useEffect(() => {
    setLiveText(''); cursor.current = 0
    if (!runId || !active) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    const refresh = () => {
      query.invalidateQueries({ queryKey: ['run', runId] })
      query.invalidateQueries({ queryKey: ['thread'] })
      query.invalidateQueries({ queryKey: ['dashboard'] })
      query.invalidateQueries({ queryKey: ['approvals'] })
    }
    async function connect() {
      try {
        const response = await fetch(`/api/v1/research/runs/${runId}/events?after=${cursor.current}`, { headers: headers(), signal: controller.signal })
        if (!response.ok || !response.body) throw new Error('stream unavailable')
        setConnection('connected')
        const reader = response.body.getReader(), decoder = new TextDecoder()
        let buffer = ''
        while (!controller.signal.aborted) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
          let split: number
          while ((split = buffer.indexOf('\n\n')) >= 0) {
            const frame = buffer.slice(0, split); buffer = buffer.slice(split + 2)
            const lines = frame.split('\n'), event = lines.find(l => l.startsWith('event:'))?.slice(6).trim()
            if (event === 'stream_end') { setConnection('complete'); refresh(); return }
            const id = Number(lines.find(l => l.startsWith('id:'))?.slice(3))
            if (id && id <= cursor.current) continue
            const data = lines.filter(l => l.startsWith('data:')).map(l => l.slice(5).trimStart()).join('\n')
            if (!data) continue
            const row = JSON.parse(data)
            if (id) cursor.current = id
            if (event === 'assistant_delta') setLiveText(previous => previous + (row.data.text || ''))
            else refresh()
          }
        }
      } catch {
        if (!controller.signal.aborted) setConnection('reconnecting')
      }
      if (!controller.signal.aborted) timer = setTimeout(connect, 2000)
    }
    connect()
    return () => { controller.abort(); if (timer) clearTimeout(timer) }
  }, [runId, active, query])
  return { liveText, connection }
}
