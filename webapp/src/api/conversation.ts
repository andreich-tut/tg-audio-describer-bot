import { api } from './client'

export interface ConversationMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export interface ConversationResponse {
  messages: ConversationMessage[]
  max_history: number
}

export const conversationApi = {
  getHistory: () => api<ConversationResponse>('/api/v1/conversation'),
  clear: () => api<{ deleted: number }>('/api/v1/conversation', { method: 'DELETE' }),
}
