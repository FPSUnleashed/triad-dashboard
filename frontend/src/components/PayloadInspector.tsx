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
      alert('Copied')
    } catch {
      alert('Copy failed')
    }
  }

  return (
    <section className="panel">
      <h2>Payload Inspector (Raw)</h2>

      <div className="step-list">
        {ordered.map((s) => (
          <button
            key={s.id}
            className={`step-pill ${selected?.id === s.id ? 'active' : ''}`}
            onClick={() => setSelectedStepId(s.id)}
          >
            {s.step_name} · attempt {s.attempt} · {s.status}
          </button>
        ))}
      </div>

      {!selected ? (
        <div className="muted">No steps yet.</div>
      ) : (
        <div className="payload-grid">
          <div>
            <div className="section-head">
              <h3>Input Payload</h3>
              <button onClick={() => copyText(selected.input_payload || '')}>Copy</button>
            </div>
            <pre>{selected.input_payload}</pre>
          </div>

          <div>
            <div className="section-head">
              <h3>Output Payload</h3>
              <button onClick={() => copyText(selected.output_payload || '')}>Copy</button>
            </div>
            <pre>{selected.output_payload || ''}</pre>
          </div>

          <div>
            <div className="section-head">
              <h3>Error</h3>
              <button onClick={() => copyText(selected.error || '')}>Copy</button>
            </div>
            <pre>{selected.error || ''}</pre>
          </div>
        </div>
      )}
    </section>
  )
}
