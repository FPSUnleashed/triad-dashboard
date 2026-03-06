import { useMemo, useState } from 'react'
import type { RunStep } from '../types'

interface Props {
  steps: RunStep[]
}

export function PayloadInspector({ steps }: Props) {
  const [selectedStepId, setSelectedStepId] = useState<number | null>(null)

  const ordered = useMemo(
    () => [...steps].sort((a, b) => a.id - b.id),
    [steps]
  )

  const selected = ordered.find((s) => s.id === selectedStepId) || ordered[ordered.length - 1]

  const copyText = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      // Silent fail
    }
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Payload Inspector</h2>
      </div>

      <div className="step-pills">
        {ordered.map((s) => (
          <button
            key={s.id}
            className={`step-pill ${selected?.id === s.id ? 'active' : ''}`}
            onClick={() => setSelectedStepId(s.id)}
          >
            {s.step_name} · #{s.attempt} · {s.status}
          </button>
        ))}
      </div>

      {!selected ? (
        <div className="text-muted text-sm">No steps yet.</div>
      ) : (
        <div className="payload-grid">
          <div className="payload-block">
            <div className="payload-block-header">
              <h3 className="payload-block-title">Input Payload</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => copyText(selected.input_payload || '')}>
                Copy
              </button>
            </div>
            <div className="payload-block-content">
              <pre>{selected.input_payload}</pre>
            </div>
          </div>

          <div className="payload-block">
            <div className="payload-block-header">
              <h3 className="payload-block-title">Output Payload</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => copyText(selected.output_payload || '')}>
                Copy
              </button>
            </div>
            <div className="payload-block-content">
              <pre>{selected.output_payload || ''}</pre>
            </div>
          </div>

          {selected.error && (
            <div className="payload-block full-width">
              <div className="payload-block-header">
                <h3 className="payload-block-title">Error</h3>
                <button className="btn btn-ghost btn-sm" onClick={() => copyText(selected.error || '')}>
                  Copy
                </button>
              </div>
              <div className="payload-block-content">
                <pre>{selected.error}</pre>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
