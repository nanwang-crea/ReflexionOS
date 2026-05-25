import { useRef, useEffect } from 'react'
import { DiffEditor } from '@monaco-editor/react'
import type { editor } from 'monaco-editor'

interface EditableDiffViewerProps {
  original: string
  modified: string
  language: string
  onChange: (value: string) => void
  onSave: () => void
}

export function EditableDiffViewer({ original, modified, language, onChange, onSave }: EditableDiffViewerProps) {
  const editorRef = useRef<editor.IStandaloneDiffEditor | null>(null)

  function handleMount(ed: editor.IStandaloneDiffEditor) {
    editorRef.current = ed

    const modifiedEditor = ed.getModifiedEditor()
    modifiedEditor.onDidChangeModelContent(() => {
      const value = modifiedEditor.getValue()
      onChange(value)
    })

    modifiedEditor.addCommand(
      2048 | 49,
      () => onSave(),
    )
  }

  useEffect(() => {
    if (editorRef.current) {
      const originalModel = editorRef.current.getOriginalEditor().getModel()
      const modifiedModel = editorRef.current.getModifiedEditor().getModel()
      if (originalModel) originalModel.setValue(original)
      if (modifiedModel) modifiedModel.setValue(modified)
    }
  }, [original, modified])

  return (
    <DiffEditor
      height="100%"
      language={language}
      original={original}
      modified={modified}
      onMount={handleMount}
      options={{
        readOnly: false,
        renderSideBySide: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineNumbers: 'on',
        automaticLayout: true,
        enableSplitViewResizing: true,
      } as editor.IDiffEditorConstructionOptions}
    />
  )
}
