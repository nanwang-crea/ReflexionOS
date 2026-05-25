import { useCallback, useEffect, useState } from 'react'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { fileApi } from '@/features/code/fileApi'
import { CodeTabBar } from './CodeTabBar'
import { DiffViewer } from './DiffViewer'
import { CodeEditor } from './CodeEditor'
import { useProjectStore } from '@/stores/projectStore'

function CodeTabEmpty() {
  return (
    <div className="flex h-full items-center justify-center text-slate-400">
      点击聊天中的文件操作查看变更
    </div>
  )
}

function CodeTabLoading() {
  return (
    <div className="flex h-full items-center justify-center text-slate-400">
      加载中...
    </div>
  )
}

export function CodeTab() {
  const activeFile = useCodeTabStore((s) => s.activeFile)
  const codeSubTab = useCodeTabStore((s) => s.codeSubTab)
  const isDirty = useCodeTabStore((s) => s.isDirty)
  const setCodeSubTab = useCodeTabStore((s) => s.setCodeSubTab)
  const setDirty = useCodeTabStore((s) => s.setDirty)

  const currentProject = useProjectStore((s) => s.currentProject)
  const projectId = currentProject?.id ?? ''

  const [original, setOriginal] = useState('')
  const [modified, setModified] = useState('')
  const [editContent, setEditContent] = useState('')
  const [language, setLanguage] = useState('plaintext')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!activeFile || !projectId) return

    const filePath = activeFile.path
    let cancelled = false
    setLoading(true)

    async function load() {
      try {
        if (codeSubTab === 'diff') {
          const resp = await fileApi.getDiffContent(projectId, filePath)
          if (cancelled) return
          const data = resp.data
          setOriginal(data.original)
          setModified(data.modified)
          setLanguage(data.language)
          setEditContent(data.modified)
        } else {
          const resp = await fileApi.getContent(projectId, filePath)
          if (cancelled) return
          const data = resp.data
          setEditContent(data.content)
          setLanguage(data.language)
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
  }, [activeFile, projectId, codeSubTab])

  const handleEditChange = useCallback(
    (newValue: string) => {
      setEditContent(newValue)
      setDirty(true)
    },
    [setDirty],
  )

  const handleSave = useCallback(async () => {
    if (!activeFile || !projectId) return
    try {
      const resp = await fileApi.writeFile({
        project_id: projectId,
        path: activeFile.path,
        content: editContent,
      })
      if (resp.data.success) {
        setDirty(false)
      } else {
        console.error('Save failed:', resp.data.error)
      }
    } catch (err) {
      console.error('Save failed:', err)
    }
  }, [activeFile, projectId, editContent, setDirty])

  if (!activeFile) {
    return <CodeTabEmpty />
  }

  const filename = activeFile.path.split('/').pop() ?? activeFile.path

  return (
    <div className="flex h-full flex-col">
      <CodeTabBar
        subTab={codeSubTab}
        onSubTabChange={setCodeSubTab}
        filename={filename}
        isDirty={isDirty}
        onSave={handleSave}
        showSave={codeSubTab === 'edit'}
      />
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <CodeTabLoading />
        ) : codeSubTab === 'diff' ? (
          <DiffViewer original={original} modified={modified} language={language} />
        ) : (
          <CodeEditor
            value={editContent}
            language={language}
            onChange={handleEditChange}
            onSave={handleSave}
          />
        )}
      </div>
    </div>
  )
}
