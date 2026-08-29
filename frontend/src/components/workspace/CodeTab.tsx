/**
 * 文件功能：代码编辑主面板
 * 文件描述：管理当前打开文件的标签栏、加载内容/diff、编辑/diff 视图切换与保存逻辑
 * 核心逻辑：根据 activeFile 的 viewMode（edit/diff）分别调用 fileApi 获取文件原始内容或 diff 内容，
 *          编辑内容通过 ref 同步（避免闭包过期），保存时按当前视图模式取最新内容写回后端
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useCodeTabStore, type ViewMode } from '@/features/code/stores/codeTab.store'
import { fileApi } from '@/features/code/api/file.api'
import { CodeTabBar } from './CodeTabBar'
import { CodeEditor } from './CodeEditor'
import { EditableDiffViewer } from './EditableDiffViewer'
import { useProjectStore } from '@/features/projects/stores/project.store'

/**
 * 组件名：CodeTabEmpty
 * 入参：无
 * 作用/渲染逻辑：未选中任何文件时展示的空状态提示
 * 返回值：JSX.Element - 提示文案
 */
function CodeTabEmpty() {
  return (
    <div className="flex h-full items-center justify-center text-content-muted">
      从左侧文件栏选择文件查看
    </div>
  )
}

/**
 * 组件名：CodeTabLoading
 * 入参：无
 * 作用/渲染逻辑：文件内容/diff 加载中展示的占位提示
 * 返回值：JSX.Element - 加载中文案
 */
function CodeTabLoading() {
  return (
    <div className="flex h-full items-center justify-center text-content-muted">
      加载中...
    </div>
  )
}

/**
 * 组件名：CodeTab
 * 入参：无（内部通过 useCodeTabStore / useProjectStore 读取状态）
 * 作用/渲染逻辑：
 *   1. 从 codeTab store 读取当前打开的文件列表与激活文件，无激活文件时展示空状态
 *   2. 激活文件变化时异步加载内容：edit 模式加载文件文本（若本地有未保存的脏内容则优先使用），
 *      diff 模式加载原始/修改后内容对比
 *   3. 提供编辑/diff 内容变更处理、保存（写回后端并清除脏标记）、切换文件、切换视图模式等回调
 *   4. 渲染 CodeTabBar 标签栏 + 对应的 CodeEditor 或 EditableDiffViewer
 * 返回值：JSX.Element - 代码编辑面板（标签栏 + 编辑器/diff 视图）
 */
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

    const file = activeFile
    const filePath = file.path
    const viewMode = file.viewMode
    const fileId = file.id
    let cancelled = false

    setLoading(true)

    async function load() {
      try {
        if (viewMode === 'edit') {
          if (file.isDirty && file.modifiedContent !== undefined) {
            if (cancelled) return
            setEditContent(file.modifiedContent)
            const lang = file.language || 'plaintext'
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
          if (file.isDirty && file.modifiedContent !== undefined) {
            setDiffModified(file.modifiedContent)
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
