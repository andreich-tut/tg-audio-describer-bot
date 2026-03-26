import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { conversationApi, ConversationMessage } from '../api/conversation'
import { useTelegram } from '../hooks/useTelegram'

export default function NotesTab() {
  const { haptic } = useTelegram()
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['conversation'],
    queryFn: conversationApi.getHistory,
    staleTime: 10_000,
  })

  const clearMutation = useMutation({
    mutationFn: conversationApi.clear,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversation'] })
      haptic?.notificationOccurred('success')
    },
  })

  const handleClear = () => {
    window.Telegram.WebApp.showConfirm(
      'Are you sure you want to clear all conversation history?',
      (ok: boolean) => {
        if (ok) clearMutation.mutate()
      },
    )
  }

  if (isLoading) return <div className="loading">Loading…</div>
  if (error) return <div className="error">Failed to load history</div>

  const messages = data?.messages ?? []

  return (
    <div className="notes-page">
      <div className="notes-header">
        <h2>Conversation History</h2>
        {messages.length > 0 && (
          <div className="notes-header-actions">
            <span className="notes-count">{messages.length} messages</span>
            <button className="btn btn-danger" onClick={handleClear} disabled={clearMutation.isPending}>
              Clear
            </button>
          </div>
        )}
      </div>

      {messages.length === 0 ? (
        <div className="notes-empty">No messages yet. Send a voice message or text to the bot to start a conversation.</div>
      ) : (
        <div className="notes-list">
          {messages.map((msg: ConversationMessage, i: number) => (
            <div key={i} className={`note-card note-${msg.role}`}>
              <div className="note-role">{msg.role === 'user' ? 'You' : 'Bot'}</div>
              <div className="note-content">{msg.content}</div>
              <div className="note-time">{new Date(msg.timestamp).toLocaleString()}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
