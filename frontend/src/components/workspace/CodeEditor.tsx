import { useRef, useEffect, useState } from 'react'
import { Editor } from '@monaco-editor/react'
import type { editor } from 'monaco-editor'
import { useThemeStore } from '@/stores/themeStore'

interface CodeEditorProps {
  content: string
  language: string
  onChange: (value: string) => void
  onSave: () => void
}

export function CodeEditor({ content, language, onChange, onSave }: CodeEditorProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null)
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

  function handleMount(ed: editor.IStandaloneCodeEditor) {
    editorRef.current = ed

    ed.onDidChangeModelContent(() => {
      onChangeRef.current(ed.getValue())
    })

    ed.addCommand(
      2048 | 49,
      () => onSaveRef.current(),
    )
  }

  return (
    <Editor
      height="100%"
      language={language}
      value={content}
      onMount={handleMount}
      theme={monacoTheme}
      options={{
        readOnly: false,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineNumbers: 'on',
        automaticLayout: true,
        wordWrap: 'on',
        tabSize: 2,
        quickSuggestions: true,
        suggestOnTriggerCharacters: true,
        parameterHints: { enabled: true },
        formatOnPaste: true,
      }}
    />
  )
}
