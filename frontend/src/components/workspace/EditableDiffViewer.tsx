import { useRef, useEffect, useState } from 'react'
import { DiffEditor } from '@monaco-editor/react'
import type { editor } from 'monaco-editor'
import { useThemeStore } from '@/stores/themeStore'

interface EditableDiffViewerProps {
  original: string
  modified: string
  language: string
  onChange: (value: string) => void
  onSave: () => void
}

export function EditableDiffViewer({ original, modified, language, onChange, onSave }: EditableDiffViewerProps) {
  const editorRef = useRef<editor.IStandaloneDiffEditor | null>(null)
  const mountedRef = useRef(false)
  const lastOriginalRef = useRef(original)
  const lastModifiedRef = useRef(modified)

  const [monacoTheme, setMonacoTheme] = useState<'vs' | 'vs-dark'>('vs')

  useEffect(() => {
    const update = () => {
      const t = useThemeStore.getState().theme
      const resolved = t === 'system'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : t
      setMonacoTheme(resolved === 'dark' ? 'vs-dark' : 'vs')
    }
    update()
    const unsub = useThemeStore.subscribe(update)
    return () => unsub()
  }, [])

  function handleMount(ed: editor.IStandaloneDiffEditor) {
    editorRef.current = ed
    mountedRef.current = true
    lastOriginalRef.current = original
    lastModifiedRef.current = modified

    const modifiedEditor = ed.getModifiedEditor()
    modifiedEditor.onDidChangeModelContent(() => {
      const value = modifiedEditor.getValue()
      lastModifiedRef.current = value
      onChange(value)
    })

    modifiedEditor.addCommand(
      2048 | 49,
      () => onSave(),
    )
  }

  useEffect(() => {
    if (!editorRef.current || !mountedRef.current) return

    const origChanged = original !== lastOriginalRef.current
    const modChanged = modified !== lastModifiedRef.current

    if (!origChanged && !modChanged) return

    const originalModel = editorRef.current.getOriginalEditor().getModel()
    const modifiedModel = editorRef.current.getModifiedEditor().getModel()

    if (origChanged && originalModel) {
      originalModel.setValue(original)
      lastOriginalRef.current = original
    }

    if (modChanged && modifiedModel) {
      const modifiedEditor = editorRef.current.getModifiedEditor()
      const currentEditValue = modifiedEditor.getValue()
      if (currentEditValue !== modified) {
        modifiedEditor.pushUndoStop()
        modifiedEditor.executeEdits('external-update', [{
          range: modifiedEditor.getModel()!.getFullModelRange(),
          text: modified,
        }])
        modifiedEditor.pushUndoStop()
      }
      lastModifiedRef.current = modified
    }
  }, [original, modified, onChange])

  return (
    <DiffEditor
      key={`${original.length}-${modified.length}`}
      height="100%"
      language={language}
      original={original}
      modified={modified}
      onMount={handleMount}
      theme={monacoTheme}
      options={{
        readOnly: false,
        renderSideBySide: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineNumbers: 'on',
        automaticLayout: true,
        enableSplitViewResizing: true,
        wordWrap: 'on',
        tabSize: 2,
        quickSuggestions: true,
        suggestOnTriggerCharacters: true,
        parameterHints: { enabled: true },
        formatOnPaste: true,
      } as editor.IDiffEditorConstructionOptions}
    />
  )
}
