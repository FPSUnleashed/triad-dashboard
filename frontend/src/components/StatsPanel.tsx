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
      } catch (e) {
        setError('Failed to load stats')
      }
    }
    fetchStats()
    const interval = setInterval(fetchStats, 10000) // Refresh every 10s
    return () => clearInterval(interval)
  }, [])

  if (error) return <div className="stats-panel error">{error}</div>
  if (!stats) return <div className="stats-panel">Loading...</div>

  const stepLabels: Record<StepName, string> = {
    planner: 'Planner',
    worker: 'Worker',
    reviewer: 'Reviewer'
  }

  return (
    <section className="stats-panel">
      <h3>📊 All-Time Stats</h3>
      <div className="stats-grid">
        {(['planner', 'worker', 'reviewer'] as StepName[]).map(step => {
          const s = stats.step_stats[step]
          return (
            <div key={step} className="stat-item">
              <div className="label">{stepLabels[step]}</div>
              <div className="value">{s.total_formatted}</div>
              <div className="label">{s.step_count} runs • avg {s.avg_formatted}</div>
            </div>
          )
        })}
      </div>
      <div className="stat-total">
        <strong>Total:</strong> {stats.total_all_steps_formatted} across {stats.total_runs} runs
      </div>
    </section>
  )
}
