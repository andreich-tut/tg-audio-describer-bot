import { useQuery } from '@tanstack/react-query'

import { usageApi, type UsageResponse } from '../api/usage'
import Section from './Section'

export default function UsageTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['usage'],
    queryFn: usageApi.getUsage,
    staleTime: 15_000,
  })

  if (isLoading) return <div className="loading">Loading…</div>
  if (error) return <div className="error">Failed to load usage data</div>
  if (!data) return null

  const usage = data as UsageResponse

  return (
    <div className="usage-page">
      <Section title="Active Models">
        <div className="usage-row">
          <span className="usage-label">LLM Model</span>
          <span className="usage-value">{usage.models.llm_model}</span>
        </div>
        <div className="usage-row">
          <span className="usage-label">LLM Provider</span>
          <span className="usage-value">{extractDomain(usage.models.llm_base_url)}</span>
        </div>
        <div className="usage-row">
          <span className="usage-label">Speech-to-Text</span>
          <span className="usage-value">{usage.models.whisper_backend}</span>
        </div>
        <div className="usage-row">
          <span className="usage-label">Whisper Model</span>
          <span className="usage-value">{usage.models.whisper_model}</span>
        </div>
      </Section>

      <Section title="Free Uses">
        <div className="usage-bar-container">
          <div className="usage-bar">
            <div
              className="usage-bar-fill"
              style={{
                width: `${Math.min(100, ((usage.free_uses.limit - usage.free_uses.count) / usage.free_uses.limit) * 100)}%`,
              }}
            />
          </div>
          <span className="usage-bar-text">
            {usage.free_uses.limit - usage.free_uses.count} of {usage.free_uses.limit} remaining
          </span>
        </div>
      </Section>

      {usage.user && (
        <Section title="Profile">
          <div className="usage-row">
            <span className="usage-label">Mode</span>
            <span className="usage-value usage-badge">{usage.user.mode}</span>
          </div>
          <div className="usage-row">
            <span className="usage-label">Language</span>
            <span className="usage-value">{usage.user.language}</span>
          </div>
        </Section>
      )}

      {usage.openrouter && (
        <Section title="OpenRouter">
          <div className="usage-row">
            <span className="usage-label">Tier</span>
            <span className="usage-value">{usage.openrouter.is_free_tier ? 'Free' : 'Paid'}</span>
          </div>
          <div className="usage-row">
            <span className="usage-label">Usage</span>
            <span className="usage-value">
              ${usage.openrouter.usage.toFixed(4)}
              {usage.openrouter.limit != null && ` / $${usage.openrouter.limit.toFixed(2)}`}
            </span>
          </div>
          {usage.openrouter.limit != null && (
            <div className="usage-bar-container">
              <div className="usage-bar">
                <div
                  className="usage-bar-fill"
                  style={{
                    width: `${Math.min(100, (usage.openrouter.usage / usage.openrouter.limit) * 100)}%`,
                  }}
                />
              </div>
            </div>
          )}
        </Section>
      )}

      {usage.groq && (
        <Section title="Groq">
          <div className="usage-row">
            <span className="usage-label">Requests</span>
            <span className="usage-value">
              {usage.groq.remaining_req} / {usage.groq.limit_req}
            </span>
          </div>
          <div className="usage-row">
            <span className="usage-label">Tokens</span>
            <span className="usage-value">
              {usage.groq.remaining_tokens} / {usage.groq.limit_tokens}
            </span>
          </div>
          <div className="usage-row">
            <span className="usage-label">Resets</span>
            <span className="usage-value">{usage.groq.reset_req}</span>
          </div>
        </Section>
      )}
    </div>
  )
}

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}
