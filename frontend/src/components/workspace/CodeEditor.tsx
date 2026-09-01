/**
 * 文件功能：单文件代码编辑器
 * 文件描述：基于 Monaco Editor 封装的普通编辑视图，支持内容变更回调与 Ctrl/Cmd+S 保存快捷键
 * 核心逻辑：通过 ref 保存最新的 onChange/onSave 回调避免闭包过期；跟随全局主题 store 动态切换
 *          Monaco 亮/暗主题；挂载后监听内容变更事件与保存快捷键命令
 */
import { useRef, useEffect, useState } from 'react'
import { Editor } from '@monaco-editor/react'
import type { editor } from 'monaco-editor'
import { useThemeStore } from '@/shared/stores/theme.store'

interface CodeEditorProps {
  content: string
  language: string
  onChange: (value: string) => void
  onSave: () => void
}

/**
 * 组件名：CodeEditor
 * 入参（props，CodeEditorProps）：
 *   - content (string): 编辑器初始/受控文本内容
 *   - language (string): 语法高亮使用的语言标识
 *   - onChange ((value: string) => void): 内容变更时的回调
 *   - onSave (() => void): 触发保存快捷键（Ctrl/Cmd+S）时的回调
 * 作用/渲染逻辑：
 *   1. 监听全局主题 store，将主题解析为 Monaco 的 'vs' / 'vs-dark' 主题
 *   2. 挂载编辑器后绑定内容变更监听与保存快捷键命令
 * 返回值：JSX.Element - Monaco 单文件编辑器
 */
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

  // 编辑器挂载完成后绑定内容变更监听，以及 Ctrl/Cmd+S 保存快捷键（2048 为 CtrlCmd 修饰符，49 为 'S' 键码）
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
