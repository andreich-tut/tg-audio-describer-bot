import { api } from './client'

export interface OpenRouterUsage {
  usage: number
  limit: number | null
  is_free_tier: boolean
  rate_limit: Record<string, unknown> | null
}

export interface GroqUsage {
  limit_req: string
  remaining_req: string
  reset_req: string
  limit_tokens: string
  remaining_tokens: string
  reset_tokens: string
}

export interface UsageResponse {
  openrouter: OpenRouterUsage | null
  groq: GroqUsage | null
  free_uses: { count: number; limit: number }
  models: {
    llm_model: string
    llm_base_url: string
    whisper_backend: string
    whisper_model: string
  }
  user: { mode: string; language: string } | null
}

export const usageApi = {
  getUsage: () => api<UsageResponse>('/api/v1/usage'),
}
