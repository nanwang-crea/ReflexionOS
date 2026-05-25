import { useRef, useEffect, useCallback } from 'react'
import Editor from '@monaco-editor/react'
import type { editor } from 'monaco-editor'

interface CodeEditorProps {
  value: string
  language: string
  onChange: (value: string) => void
  onSave: () => void
}

export function CodeEditor({ value, language, onChange, onSave }: CodeEditorProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null)

  function handleMount(editorInstance: editor.IStandaloneCodeEditor) {
    editorRef.current = editorInstance
    editorInstance.addCommand(
      2048 | 49,
      () => onSave(),
    )
  }

  useEffect(() => {
    if (editorRef.current) {
      const model = editorRef.current.getModel()
      if (model && model.getValue() !== value) {
        editorRef.current.setValue(value)
      }
    }
  }, [value])

  const handleChange = useCallback(
    (newValue: string | undefined) => {
      onChange(newValue ?? '')
    },
    [onChange],
  )

  return (
    <Editor
      height="100%"
      language={language}
      value={value}
      onChange={handleChange}
      onMount={handleMount}
      options={{
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineNumbers: 'on',
        automaticLayout: true,
        wordWrap: 'on',
        tabSize: 2,
      }}
    />
  )
}
