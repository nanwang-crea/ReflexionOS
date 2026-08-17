/**
 * 文件功能：单个终端实例组件（基于 xterm.js）
 * 文件描述：渲染并管理一个 xterm 终端实例，负责主题切换、自适应尺寸、与主进程 PTY 之间的数据收发
 * 核心逻辑：挂载时创建 xterm.Terminal 与 FitAddon，通过 terminalIpc 与后端 PTY 建立数据通道
 *          （若 PTY 已存在则复用，否则新建），监听主题变化与容器尺寸变化并同步更新；卸载时清理所有订阅与终端实例
 */
import { useEffect, useRef, useCallback } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { useTerminalStore } from '@/features/terminal/stores/terminal.store'
import { useThemeStore } from '@/shared/stores/theme.store'
import { terminalIpc } from '@/services/terminalIpc'
import '@xterm/xterm/css/xterm.css'

const DARK_THEME = {
  background: '#1e1e2e',
  foreground: '#cdd6f4',
  cursor: '#f5e0dc',
  cursorAccent: '#1e1e2e',
  selectionBackground: '#585b70',
  selectionForeground: '#cdd6f4',
  black: '#45475a',
  red: '#f38ba8',
  green: '#a6e3a1',
  yellow: '#f9e2af',
  blue: '#89b4fa',
  magenta: '#f5c2e7',
  cyan: '#94e2d5',
  white: '#bac2de',
  brightBlack: '#585b70',
  brightRed: '#f38ba8',
  brightGreen: '#a6e3a1',
  brightYellow: '#f9e2af',
  brightBlue: '#89b4fa',
  brightMagenta: '#f5c2e7',
  brightCyan: '#94e2d5',
  brightWhite: '#a6adc8',
}

const LIGHT_THEME = {
  background: '#fafafa',
  foreground: '#383a42',
  cursor: '#526fff',
  cursorAccent: '#fafafa',
  selectionBackground: '#add6ff',
  selectionForeground: '#383a42',
  black: '#383a42',
  red: '#e45649',
  green: '#50a14f',
  yellow: '#c18401',
  blue: '#4078f2',
  magenta: '#a626a4',
  cyan: '#0184bc',
  white: '#a0a1a7',
  brightBlack: '#4f525e',
  brightRed: '#e06c75',
  brightGreen: '#98c379',
  brightYellow: '#e5c07b',
  brightBlue: '#61afef',
  brightMagenta: '#c678dd',
  brightCyan: '#56b6c2',
  brightWhite: '#080a0e',
}

/**
 * 函数名：getResolvedTheme
 * 入参：无
 * 功能：解析当前实际应使用的终端主题（浅色/深色）
 * 运行逻辑：读取主题 store 中的设置，若为 'system' 则依据系统的 prefers-color-scheme 媒体查询判断，否则直接返回设置值
 * 出参：'light' | 'dark' - 解析后的主题
 */
function getResolvedTheme(): 'light' | 'dark' {
  const mode = useThemeStore.getState().theme
  if (mode === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return mode
}

interface TerminalInstanceProps {
  terminalId: string
}

/**
 * 组件名：TerminalInstance
 * 入参（props）：
 *   - terminalId (string): 终端实例的唯一标识，用于与 store 及后端 PTY 关联
 * 作用/渲染逻辑：
 *   1. 挂载时创建 xterm.Terminal 实例与 FitAddon，按当前主题设置颜色方案，并挂载到容器 DOM
 *   2. 订阅主题变化（切换终端配色）、PTY 数据（写入终端）、PTY 退出事件（提示退出码并标记状态）
 *   3. 监听终端输入并通过 terminalIpc 转发给后端 PTY；通过 ResizeObserver 监听容器尺寸变化并自适应调整
 *   4. 首次挂载时检测 PTY 是否已存活：存活则直接 resize 复用，否则以当前终端的 cwd 创建新 PTY 并记录 pid
 *   5. 卸载时清理 ResizeObserver、各类订阅，并销毁 xterm 实例
 * 返回值：JSX.Element - 承载 xterm 终端的容器 div
 */
export function TerminalInstance({ terminalId }: TerminalInstanceProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const setPtyPid = useTerminalStore((s) => s.setPtyPid)
  const markExited = useTerminalStore((s) => s.markExited)
  const cwd = useTerminalStore(
    (s) => s.instances.find((t) => t.id === terminalId)?.cwd ?? '',
  )

  // 处理终端尺寸自适应：调用 FitAddon 重新计算行列数，并同步给后端 PTY
  const handleResize = useCallback(() => {
    if (fitAddonRef.current && termRef.current) {
      try {
        fitAddonRef.current.fit()
        const { cols, rows } = termRef.current
        terminalIpc.resize(terminalId, cols, rows)
      } catch (_e) { /* resize may fail during unmount */ }
    }
  }, [terminalId])

  useEffect(() => {
    if (!containerRef.current) return

    let active = true

    const resolved = getResolvedTheme()
    const term = new Terminal({
      theme: resolved === 'dark' ? DARK_THEME : LIGHT_THEME,
      fontSize: 13,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      cursorBlink: true,
      scrollback: 5000,
    })

    const fitAddon = new FitAddon()
    term.loadAddon(fitAddon)
    term.open(containerRef.current)
    fitAddon.fit()

    termRef.current = term
    fitAddonRef.current = fitAddon

    const unsubTheme = useThemeStore.subscribe((state) => {
      const next = state.theme === 'system'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : state.theme
      if (termRef.current) {
        termRef.current.options.theme = next === 'dark' ? DARK_THEME : LIGHT_THEME
      }
    })

    const unsubData = terminalIpc.onData((id, data) => {
      if (id === terminalId && active) {
        term.write(data)
      }
    })

    const unsubExit = terminalIpc.onExit((id, exitCode) => {
      if (id === terminalId && active) {
        term.writeln(`\r\n\x1b[33m进程已退出 (code=${exitCode})\x1b[0m`)
        markExited(terminalId)
      }
    })

    term.onData((data) => {
      if (active) {
        terminalIpc.write(terminalId, data)
      }
    })

    terminalIpc.isAlive(terminalId).then((alive) => {
      if (!active) return
      if (alive) {
        handleResize()
        return
      }
      terminalIpc.create(terminalId, cwd).then(({ pid }) => {
        if (active) {
          setPtyPid(terminalId, pid)
        }
      }).catch((err) => {
        if (active) {
          term.writeln(`\x1b[31m终端创建失败: ${err.message}\x1b[0m`)
        }
      })
    })

    const resizeObserver = new ResizeObserver(() => {
      handleResize()
    })
    resizeObserver.observe(containerRef.current)

    return () => {
      active = false
      resizeObserver.disconnect()
      unsubTheme()
      unsubData()
      unsubExit()
      term.dispose()
      termRef.current = null
      fitAddonRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [terminalId])

  return (
    <div ref={containerRef} className="h-full w-full" />
  )
}
