import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Stats, StepName } from '../types'

export function StatsPanel() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await api.getStats()
        setStats(data)
        setError(null)
      } catch {
        setError('Failed to load stats')
      }
    }
    fetchStats()
    const interval = setInterval(fetchStats, 10000)
    return () => clearInterval(interval)
  }, [])

  if (error) return (
    <section className="panel stats-panel">
      <div className="text-sm text-muted">{error}</div>
    </section>
  )
  
  if (!stats) return (
    <section className="panel stats-panel">
      <div className="text-sm text-muted">Loading stats...</div>
    </section>
  )

  const stepLabels: Record<StepName, string> = {
    planner: 'Planner',
    worker: 'Worker',
    reviewer: 'Reviewer'
  }

  return (
    <section className="panel stats-panel">
      <div className="stats-header">
        <h3 className="stats-title">All-Time Stats</h3>
      </div>
      <div className="stats-grid">
        {(['planner', 'worker', 'reviewer'] as StepName[]).map(step => {
          const s = stats.step_stats[step]
          return (
            <div key={step} className="stat-card">
              <div className="stat-label">{stepLabels[step]}</div>
              <div className="stat-value">{s.total_formatted}</div>
              <div className="stat-meta">{s.step_count} runs · avg {s.avg_formatted}</div>
            </div>
          )
        })}
      </div>
      <div className="stats-total">
        <strong>Total:</strong> {stats.total_all_steps_formatted} across {stats.total_runs} runs
      </div>
    </section>
  )
}
