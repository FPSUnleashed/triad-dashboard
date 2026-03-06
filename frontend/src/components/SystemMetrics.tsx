import { useEffect, useState } from 'react'
import { api } from '../api'
import type { SystemMetrics as SystemMetricsType } from '../types'

export function SystemMetrics() {
  const [metrics, setMetrics] = useState<SystemMetricsType | null>(null)

  useEffect(() => {
    let mounted = true
    const poll = async () => {
      try {
        const data = await api.getSystemMetrics()
        if (mounted) setMetrics(data)
      } catch {
        // silent fail on polling
      }
    }
    poll()
    const interval = setInterval(poll, 1000)
    return () => { mounted = false; clearInterval(interval) }
  }, [])

  if (!metrics) return null

  const cpuColor = metrics.cpu_percent > 80 ? 'var(--accent-danger)'
    : metrics.cpu_percent > 50 ? 'var(--accent-warn)'
    : 'var(--accent-ok)'

  const ramColor = metrics.ram_percent > 85 ? 'var(--accent-danger)'
    : metrics.ram_percent > 60 ? 'var(--accent-warn)'
    : 'var(--accent-ok)'

  return (
    <div className="sys-metrics">
      <div className="sys-metric" title={`CPU: ${metrics.cpu_percent}%`}>
        <span className="sys-metric-icon">⚡</span>
        <span className="sys-metric-label">CPU</span>
        <span className="sys-metric-bar">
          <span className="sys-metric-fill" style={{ width: `${metrics.cpu_percent}%`, backgroundColor: cpuColor }} />
        </span>
        <span className="sys-metric-val">{metrics.cpu_percent}%</span>
      </div>

      <div className="sys-metric" title={`RAM: ${metrics.ram_used_gb}/${metrics.ram_total_gb} GB`}>
        <span className="sys-metric-icon">🧠</span>
        <span className="sys-metric-label">RAM</span>
        <span className="sys-metric-bar">
          <span className="sys-metric-fill" style={{ width: `${metrics.ram_percent}%`, backgroundColor: ramColor }} />
        </span>
        <span className="sys-metric-val">{metrics.ram_used_gb}G</span>
      </div>

      <div className={`sys-vm-badge ${metrics.vm_running ? 'vm-on' : 'vm-off'}`}
           title={metrics.vm_running
             ? `VM running (PID ${metrics.vm_info.pid || '?'}, ${metrics.vm_info.ram_alloc || '?'} RAM${metrics.vm_info.kvm ? ', KVM' : ''})` 
             : 'VM offline'}>
        <span className="sys-vm-dot" />
        <span className="sys-vm-text">
          {metrics.vm_running ? (metrics.vm_info.kvm ? 'VM · KVM' : 'VM · TCG') : 'VM OFF'}
        </span>
      </div>
    </div>
  )
}
