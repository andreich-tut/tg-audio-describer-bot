import { useEffect, useState, useCallback } from 'react'

export interface OAuthState {
  provider: string
  connected: boolean
  login: string | null
}

/**
 * Hook for real-time OAuth state updates via SSE.
 * Falls back to polling if SSE is unavailable.
 */
export function useOAuthSSE(initData: string) {
  const [state, setState] = useState<OAuthState | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchState = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/settings', {
        headers: {
          Authorization: `tma ${initData}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setState({
          provider: 'yandex',
          connected: !!data.oauth?.yandex?.connected,
          login: data.oauth?.yandex?.login || null,
        })
      }
    } catch (error) {
      console.error('Failed to fetch OAuth state:', error)
    } finally {
      setLoading(false)
    }
  }, [initData])

  useEffect(() => {
    const url = `/api/v1/oauth/events?auth=${encodeURIComponent(initData)}`
    let es: EventSource | null = null

    try {
      es = new EventSource(url)

      es.addEventListener('oauth_state', (e) => {
        const data = JSON.parse(e.data)
        setState(data)
        setLoading(false)
      })

      es.onerror = () => {
        console.warn('SSE connection error, will reconnect...')
        es?.close()
        // Reconnect after 3s
        setTimeout(() => fetchState(), 3000)
      }
    } catch (error) {
      console.warn('SSE not available, using fallback:', error)
      fetchState()
    }

    // Fallback: refetch on tab visibility change
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        fetchState()
      }
    }
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      es?.close()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [initData, fetchState])

  return { state, loading, refetch: fetchState }
}
