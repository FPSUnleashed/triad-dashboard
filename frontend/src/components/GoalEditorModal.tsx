import { useEffect, useRef, useCallback } from 'react'
import Editor from '@toast-ui/editor'
import '@toast-ui/editor/dist/toastui-editor.css'

interface Props {
  value: string
  onChange: (v: string) => void
  onClose: () => void
}

export function GoalEditorModal({ value, onChange, onClose }: Props) {
  const mountRef = useRef<HTMLDivElement | null>(null)
  const editorRef = useRef<Editor | null>(null)
  const backdropRef = useRef<HTMLDivElement | null>(null)

  // Save current editor content and close
  const handleSave = useCallback(() => {
    if (editorRef.current) {
      onChange(editorRef.current.getMarkdown())
    }
    onClose()
  }, [onChange, onClose])

  // Escape key closes (saves)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleSave()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [handleSave])

  // Init toast-ui editor
  useEffect(() => {
    if (!mountRef.current || editorRef.current) return

    const editor = new Editor({
      el: mountRef.current,
      height: '100%',
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

    editorRef.current = editor

    return () => {
      editor.destroy()
      editorRef.current = null
    }
  }, [])

  // Sync external value changes
  useEffect(() => {
    const editor = editorRef.current
    if (!editor) return
    if (editor.getMarkdown() !== (value || '')) {
      editor.setMarkdown(value || '')
    }
  }, [value])

  // Click on backdrop = save & close
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === backdropRef.current) handleSave()
  }

  return (
    <div
      className="goal-modal-backdrop"
      ref={backdropRef}
      onClick={handleBackdropClick}
    >
      <div className="goal-modal">
        <div className="goal-modal-header">
          <h3 className="goal-modal-title">Edit Goal</h3>
          <div className="goal-modal-actions">
            <button className="btn btn-primary btn-sm" onClick={handleSave}>
              Save & Close
            </button>
            <button className="btn btn-ghost btn-sm" onClick={handleSave}>
              ✕
            </button>
          </div>
        </div>
        <div className="goal-modal-body md-rich-wrap">
          <div ref={mountRef} />
        </div>
      </div>
    </div>
  )
}
