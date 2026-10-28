// A Markdown text editor with two modes: Write (the text and a formatting toolbar) and
// Preview (the text rendered). It takes Markdown text and gives back Markdown text; nothing
// outside depends on how it edits or renders, so it can be replaced by another editor whole.
import { type KeyboardEvent, lazy, Suspense, useEffect, useRef, useState } from 'react'
import { type Edit, type Format, format } from './formatting'
import './markdown-editor.css'

const Preview = lazy(() => import('./Preview'))

type Mode = 'write' | 'preview'

const TOOLS: { format: Format; label: string; face: string; shortcut?: string }[] = [
  { format: 'bold', label: 'Bold', face: 'B', shortcut: 'B' },
  { format: 'italic', label: 'Italic', face: 'I', shortcut: 'I' },
  { format: 'title', label: 'Title', face: 'H1' },
  { format: 'heading', label: 'Heading', face: 'H2' },
  { format: 'subheading', label: 'Subheading', face: 'H3' },
  { format: 'bullets', label: 'Bulleted list', face: '• List' },
  { format: 'numbers', label: 'Numbered list', face: '1. List' },
  { format: 'link', label: 'Link', face: 'Link', shortcut: 'K' },
]

const SHORTCUTS = new Map(
  TOOLS.flatMap((tool) => (tool.shortcut ? [[tool.shortcut.toLowerCase(), tool.format] as const] : [])),
)

const SHORTCUT_KEY = /Mac|iPhone|iPad/.test(navigator.userAgent) ? '⌘' : 'Ctrl+'

export function MarkdownEditor({
  value,
  onChange,
  label,
}: {
  value: string
  onChange: (value: string) => void
  label: string
}) {
  // Opens on the rendered text, or on Write when there is nothing to render yet
  const [mode, setMode] = useState<Mode>(() => (value.trim() ? 'preview' : 'write'))
  const area = useRef<HTMLTextAreaElement>(null)
  const focusArea = useRef(false)

  useEffect(() => {
    if (mode === 'write' && focusArea.current) area.current?.focus()
    focusArea.current = false
  }, [mode])

  function switchTo(next: Mode) {
    focusArea.current = next === 'write'
    setMode(next)
  }

  function run(kind: Format) {
    const el = area.current
    if (!el) return
    apply(el, format(kind, { value: el.value, start: el.selectionStart, end: el.selectionEnd }))
  }

  /** Make the edit as if typed, so the browser's undo takes it back. */
  function apply(el: HTMLTextAreaElement, edit: Edit) {
    el.focus()
    if (edit.insert !== el.value.slice(edit.from, edit.to)) {
      el.setSelectionRange(edit.from, edit.to)
      const typed =
        edit.insert === ''
          ? document.execCommand('delete')
          : document.execCommand('insertText', false, edit.insert)
      if (!typed) {
        el.setRangeText(edit.insert, edit.from, edit.to)
        onChange(el.value)
      }
    }
    el.setSelectionRange(...edit.select)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return
    const kind = SHORTCUTS.get(event.key.toLowerCase())
    if (kind) {
      event.preventDefault()
      run(kind)
    }
  }

  return (
    <div className="markdown-editor">
      <div className="markdown-editor-bar">
        <div className="segmented" role="group" aria-label="Mode">
          <button type="button" aria-pressed={mode === 'write'} onClick={() => switchTo('write')}>
            Write
          </button>
          <button type="button" aria-pressed={mode === 'preview'} onClick={() => switchTo('preview')}>
            Preview
          </button>
        </div>
        {mode === 'write' && (
          <div className="markdown-editor-tools" role="toolbar" aria-label="Formatting">
            {TOOLS.map((tool) => (
              <button
                key={tool.format}
                type="button"
                className={`tool-${tool.format}`}
                aria-label={tool.label}
                title={tool.shortcut ? `${tool.label} (${SHORTCUT_KEY}${tool.shortcut})` : tool.label}
                // Keep the focus, and so the selection, in the text
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => run(tool.format)}
              >
                {tool.face}
              </button>
            ))}
          </div>
        )}
      </div>
      {/* Kept mounted while previewing, so its undo history survives a switch of modes */}
      <textarea
        ref={area}
        className="document"
        aria-label={label}
        rows={24}
        hidden={mode !== 'write'}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
      />
      {mode === 'preview' && (
        <div className="markdown-editor-preview" role="region" aria-label={`${label} preview`}>
          {value.trim() ? (
            <Suspense fallback={null}>
              <Preview markdown={value} />
            </Suspense>
          ) : (
            <p className="hint">Nothing written yet.</p>
          )}
        </div>
      )}
    </div>
  )
}
