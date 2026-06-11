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
  const onChangeRef = useRef(onChange)
  const onSaveRef = useRef(onSave)

  onChangeRef.current = onChange
  onSaveRef.current = onSave

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

    const modifiedEditor = ed.getModifiedEditor()
    modifiedEditor.onDidChangeModelContent(() => {
      onChangeRef.current(modifiedEditor.getValue())
    })

    modifiedEditor.addCommand(
      2048 | 49,
      () => onSaveRef.current(),
    )
  }

  return (
    <DiffEditor
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
        quickSuggestions: true,
        suggestOnTriggerCharacters: true,
        parameterHints: { enabled: true },
        formatOnPaste: true,
      } satisfies editor.IDiffEditorConstructionOptions}
    />
  )
}
