import { useEffect, useRef, useCallback } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { useTerminalStore } from '@/features/terminal/terminalStore'
import { useThemeStore } from '@/stores/themeStore'
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

export function TerminalInstance({ terminalId }: TerminalInstanceProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const setPtyPid = useTerminalStore((s) => s.setPtyPid)
  const markExited = useTerminalStore((s) => s.markExited)
  const cwd = useTerminalStore(
    (s) => s.instances.find((t) => t.id === terminalId)?.cwd ?? '',
  )

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
