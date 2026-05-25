import { useRef, useEffect } from 'react'
import { DiffEditor } from '@monaco-editor/react'
import type { editor } from 'monaco-editor'

interface DiffViewerProps {
  original: string
  modified: string
  language: string
}

export function DiffViewer({ original, modified, language }: DiffViewerProps) {
  const editorRef = useRef<editor.IStandaloneDiffEditor | null>(null)

  function handleMount(ed: editor.IStandaloneDiffEditor) {
    editorRef.current = ed
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
        readOnly: true,
        renderSideBySide: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineNumbers: 'on',
        automaticLayout: true,
      } as editor.IDiffEditorConstructionOptions}
    />
  )
}
