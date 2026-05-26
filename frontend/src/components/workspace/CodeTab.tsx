import { useCallback, useEffect, useRef, useState } from 'react'
import { useCodeTabStore, type ViewMode } from '@/features/code/codeTabStore'
import { fileApi } from '@/features/code/fileApi'
import { CodeTabBar } from './CodeTabBar'
import { CodeEditor } from './CodeEditor'
import { EditableDiffViewer } from './EditableDiffViewer'
import { useProjectStore } from '@/stores/projectStore'

function CodeTabEmpty() {
  return (
    <div className="flex h-full items-center justify-center text-content-muted">
      从左侧文件栏选择文件查看
    </div>
  )
}

function CodeTabLoading() {
  return (
    <div className="flex h-full items-center justify-center text-content-muted">
      加载中...
    </div>
  )
}

export function CodeTab() {
  const openFiles = useCodeTabStore((s) => s.openFiles)
  const activeFileId = useCodeTabStore((s) => s.activeFileId)
  const activeFile = useCodeTabStore((s) => s.activeFile)
  const closeFile = useCodeTabStore((s) => s.closeFile)
  const setViewMode = useCodeTabStore((s) => s.setViewMode)
  const setDirty = useCodeTabStore((s) => s.setDirty)
  const clearDirty = useCodeTabStore((s) => s.clearDirty)
  const setFileLanguage = useCodeTabStore((s) => s.setFileLanguage)

  const currentProject = useProjectStore((s) => s.currentProject)
  const projectId = currentProject?.id ?? ''

  const [editContent, setEditContent] = useState('')
  const [diffOriginal, setDiffOriginal] = useState('')
  const [diffModified, setDiffModified] = useState('')
  const [language, setLanguage] = useState('plaintext')
  const [loading, setLoading] = useState(false)

  const editContentRef = useRef(editContent)
  const diffModifiedRef = useRef(diffModified)

  useEffect(() => { editContentRef.current = editContent }, [editContent])
  useEffect(() => { diffModifiedRef.current = diffModified }, [diffModified])

  useEffect(() => {
    if (!activeFile || !projectId) return

    const filePath = activeFile.path
    const viewMode = activeFile.viewMode
    const fileId = activeFile.id
    let cancelled = false

    setLoading(true)

    async function load() {
      try {
        if (viewMode === 'edit') {
          if (activeFile.isDirty && activeFile.modifiedContent !== undefined) {
            if (cancelled) return
            setEditContent(activeFile.modifiedContent)
            const lang = activeFile.language || 'plaintext'
            setLanguage(lang)
            setDiffOriginal('')
            setDiffModified('')
          } else {
            const resp = await fileApi.getContent(projectId, filePath)
            if (cancelled) return
            setEditContent(resp.data.content)
            setLanguage(resp.data.language)
            setFileLanguage(fileId, resp.data.language)
            setDiffOriginal('')
            setDiffModified('')
          }
        } else {
          const resp = await fileApi.getDiffContent(projectId, filePath)
          if (cancelled) return
          setDiffOriginal(resp.data.original)
          if (activeFile.isDirty && activeFile.modifiedContent !== undefined) {
            setDiffModified(activeFile.modifiedContent)
          } else {
            setDiffModified(resp.data.modified)
          }
          setLanguage(resp.data.language)
          setFileLanguage(fileId, resp.data.language)
          setEditContent('')
        }
      } catch (err) {
        if (cancelled) return
        console.error('Failed to load file:', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [activeFileId, activeFile?.path, activeFile?.viewMode, projectId])

  const handleEditChange = useCallback(
    (value: string) => {
      setEditContent(value)
      editContentRef.current = value
      if (activeFileId) setDirty(activeFileId, true, value)
    },
    [activeFileId, setDirty],
  )

  const handleDiffChange = useCallback(
    (value: string) => {
      setDiffModified(value)
      diffModifiedRef.current = value
      if (activeFileId) setDirty(activeFileId, true, value)
    },
    [activeFileId, setDirty],
  )

  const handleSave = useCallback(async () => {
    if (!activeFile || !projectId || !activeFileId) return
    const content = activeFile.viewMode === 'edit'
      ? editContentRef.current
      : diffModifiedRef.current
    if (content === undefined) return
    try {
      const resp = await fileApi.writeFile({
        project_id: projectId,
        path: activeFile.path,
        content,
      })
      if (resp.data.success) {
        clearDirty(activeFileId)
      } else {
        console.error('Save failed:', resp.data.error)
      }
    } catch (err) {
      console.error('Save failed:', err)
    }
  }, [activeFile, activeFileId, projectId, clearDirty])

  const handleSelectFile = useCallback(
    (id: string) => {
      const file = openFiles.find((f) => f.id === id)
      if (file) {
        useCodeTabStore.setState({
          activeFileId: id,
          activeFile: file,
        })
      }
    },
    [openFiles],
  )

  const handleToggleViewMode = useCallback(() => {
    if (!activeFileId || !activeFile) return
    const nextMode: ViewMode = activeFile.viewMode === 'edit' ? 'diff' : 'edit'
    setViewMode(activeFileId, nextMode)
  }, [activeFileId, activeFile, setViewMode])

  if (!activeFile) {
    return <CodeTabEmpty />
  }

  return (
    <div className="flex h-full flex-col">
      <CodeTabBar
        openFiles={openFiles}
        activeFileId={activeFileId}
        viewMode={activeFile.viewMode}
        onSelectFile={handleSelectFile}
        onCloseFile={closeFile}
        onToggleViewMode={handleToggleViewMode}
      />
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <CodeTabLoading />
        ) : activeFile.viewMode === 'edit' ? (
          <CodeEditor
            key={activeFileId}
            content={editContent}
            language={language}
            onChange={handleEditChange}
            onSave={handleSave}
          />
        ) : (
          <EditableDiffViewer
            key={activeFileId}
            original={diffOriginal}
            modified={diffModified}
            language={language}
            onChange={handleDiffChange}
            onSave={handleSave}
          />
        )}
      </div>
    </div>
  )
}
