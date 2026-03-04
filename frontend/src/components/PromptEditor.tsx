import { useEffect, useRef, useState } from 'react'
import Editor from '@toast-ui/editor'
import '@toast-ui/editor/dist/toastui-editor.css'
import type { Profile } from '../types'

interface Props {
  profiles: Profile[]
  selectedProfileId: number | null
  profileName: string
  plannerPrompt: string
  workerPrompt: string
  reviewerPrompt: string
  onSelectProfile: (id: number) => void
  onProfileNameChange: (v: string) => void
  onPlannerChange: (v: string) => void
  onWorkerChange: (v: string) => void
  onReviewerChange: (v: string) => void
  onSave: () => void
}

function calcEditorHeight(markdown: string): string {
  const lines = (markdown || '').split('\n').length
  const estimated = 120 + lines * 22
  const px = Math.max(280, estimated)
  return `${px}px`
}

function PromptSection({
  label,
  value,
  onChange,
  collapsed,
  onToggle
}: {
  label: string
  value: string
  onChange: (v: string) => void
  collapsed: boolean
  onToggle: () => void
}) {
  const mountRef = useRef<HTMLDivElement | null>(null)
  const editorRef = useRef<Editor | null>(null)

  useEffect(() => {
    if (!mountRef.current || editorRef.current || collapsed) return

    const editor = new Editor({
      el: mountRef.current,
      height: calcEditorHeight(value || ''),
      initialEditType: 'wysiwyg',
      previewStyle: 'vertical',
      usageStatistics: false,
      initialValue: value || '',
      toolbarItems: [
        ['heading', 'bold', 'italic', 'strike'],
        ['hr', 'quote'],
        ['ul', 'ol', 'task'],
        ['table', 'link'],
        ['code', 'codeblock']
      ]
    })

    editor.on('change', () => {
      const md = editor.getMarkdown()
      onChange(md)
      editor.setHeight(calcEditorHeight(md))
    })

    editorRef.current = editor

    return () => {
      editor.destroy()
      editorRef.current = null
    }
  }, [collapsed])

  useEffect(() => {
    const editor = editorRef.current
    if (!editor) return
    const incoming = value || ''
    const current = editor.getMarkdown()
    if (current !== incoming) {
      editor.setMarkdown(incoming)
    }
    editor.setHeight(calcEditorHeight(incoming))
  }, [value])

  const lineCount = value ? value.split('\n').length : 0
  const charCount = value ? value.length : 0

  return (
    <div className="prompt-section">
      <div className="prompt-toolbar">
        <label className="label">{label}</label>
        <button type="button" className="prompt-toggle-btn" onClick={onToggle}>
          {collapsed ? 'Expand' : 'Collapse'}
        </button>
      </div>

      {collapsed ? (
        <div className="prompt-collapsed-meta muted small">
          Collapsed · {lineCount} lines · {charCount} chars
        </div>
      ) : (
        <div className="md-rich-wrap">
          <div ref={mountRef} />
        </div>
      )}
    </div>
  )
}

export function PromptEditor(props: Props) {
  const [collapsed, setCollapsed] = useState({
    planner: true,
    worker: true,
    reviewer: true
  })

  return (
    <section className="panel">
      <h2>Prompt Editor</h2>

      <div className="row">
        <label>Profile</label>
        <select
          value={props.selectedProfileId ?? ''}
          onChange={(e) => props.onSelectProfile(Number(e.target.value))}
        >
          <option value="" disabled>
            Select profile
          </option>
          {props.profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      <div className="row">
        <label>Save As Name</label>
        <input
          value={props.profileName}
          onChange={(e) => props.onProfileNameChange(e.target.value)}
          placeholder="default"
        />
        <button onClick={props.onSave}>Save Profile</button>
      </div>

      <p className="muted small">Rich Markdown editor enabled: formatted content + direct editing in one field.</p>

      <PromptSection
        label="Planner Prompt"
        value={props.plannerPrompt}
        onChange={props.onPlannerChange}
        collapsed={collapsed.planner}
        onToggle={() => setCollapsed((v) => ({ ...v, planner: !v.planner }))}
      />
      <PromptSection
        label="Worker Prompt"
        value={props.workerPrompt}
        onChange={props.onWorkerChange}
        collapsed={collapsed.worker}
        onToggle={() => setCollapsed((v) => ({ ...v, worker: !v.worker }))}
      />
      <PromptSection
        label="Reviewer Prompt"
        value={props.reviewerPrompt}
        onChange={props.onReviewerChange}
        collapsed={collapsed.reviewer}
        onToggle={() => setCollapsed((v) => ({ ...v, reviewer: !v.reviewer }))}
      />
    </section>
  )
}
