import { useCallback, useEffect, useState } from 'react'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { fileApi } from '@/features/code/fileApi'
import { CodeTabBar } from './CodeTabBar'
import { EditableDiffViewer } from './EditableDiffViewer'
import { useProjectStore } from '@/stores/projectStore'

function CodeTabEmpty() {
  return (
    <div className="flex h-full items-center justify-center text-slate-400">
      从左侧文件栏选择文件查看变更
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
  const isDirty = useCodeTabStore((s) => s.isDirty)
  const setDirty = useCodeTabStore((s) => s.setDirty)

  const currentProject = useProjectStore((s) => s.currentProject)
  const projectId = currentProject?.id ?? ''

  const [original, setOriginal] = useState('')
  const [modified, setModified] = useState('')
  const [language, setLanguage] = useState('plaintext')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!activeFile || !projectId) return

    const filePath = activeFile.path
    let cancelled = false
    setLoading(true)

    async function load() {
      try {
        const resp = await fileApi.getDiffContent(projectId, filePath)
        if (cancelled) return
        const data = resp.data
        setOriginal(data.original)
        setModified(data.modified)
        setLanguage(data.language)
      } catch (err) {
        if (cancelled) return
        console.error('Failed to load file:', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [activeFile, projectId])

  const handleChange = useCallback(
    (value: string) => {
      setModified(value)
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
        content: modified,
      })
      if (resp.data.success) {
        setDirty(false)
      } else {
        console.error('Save failed:', resp.data.error)
      }
    } catch (err) {
      console.error('Save failed:', err)
    }
  }, [activeFile, projectId, modified, setDirty])

  if (!activeFile) {
    return <CodeTabEmpty />
  }

  const filename = activeFile.path.split('/').pop() ?? activeFile.path

  return (
    <div className="flex h-full flex-col">
      <CodeTabBar
        filename={filename}
        isDirty={isDirty}
        onSave={handleSave}
      />
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <CodeTabLoading />
        ) : (
          <EditableDiffViewer
            original={original}
            modified={modified}
            language={language}
            onChange={handleChange}
            onSave={handleSave}
          />
        )}
      </div>
    </div>
  )
}
