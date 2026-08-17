/**
 * 文件功能：可编辑的 Diff 对比编辑器
 * 文件描述：基于 Monaco DiffEditor 封装的并排对比视图，右侧（modified）可编辑，支持变更回调与保存快捷键
 * 核心逻辑：通过 ref 保存最新的 onChange/onSave 回调避免闭包过期；跟随全局主题 store 动态切换
 *          Monaco 亮/暗主题；挂载后只监听右侧编辑器的内容变更与保存快捷键
 */
import { useRef, useEffect, useState } from 'react'
import { DiffEditor } from '@monaco-editor/react'
import type { editor } from 'monaco-editor'
import { useThemeStore } from '@/shared/stores/theme.store'

interface EditableDiffViewerProps {
  original: string
  modified: string
  language: string
  onChange: (value: string) => void
  onSave: () => void
}

/**
 * 组件名：EditableDiffViewer
 * 入参（props，EditableDiffViewerProps）：
 *   - original (string): 对比左侧的原始内容（只读）
 *   - modified (string): 对比右侧的修改后内容（可编辑）
 *   - language (string): 语法高亮使用的语言标识
 *   - onChange ((value: string) => void): 右侧内容变更时的回调
 *   - onSave (() => void): 触发保存快捷键（Ctrl/Cmd+S）时的回调
 * 作用/渲染逻辑：
 *   1. 监听全局主题 store，将主题解析为 Monaco 的 'vs' / 'vs-dark' 主题
 *   2. 挂载编辑器后获取右侧（modified）编辑器实例，绑定内容变更监听与保存快捷键命令
 * 返回值：JSX.Element - Monaco 并排 Diff 编辑器
 */
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

  // 编辑器挂载完成后取右侧（modified）编辑器实例，绑定内容变更监听与保存快捷键（2048 为 CtrlCmd 修饰符，49 为 'S' 键码）
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
