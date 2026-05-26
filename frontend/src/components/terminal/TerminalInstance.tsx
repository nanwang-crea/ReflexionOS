import { useEffect, useRef, useCallback } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { useTerminalStore } from '@/features/terminal/terminalStore'
import { terminalIpc } from '@/services/terminalIpc'
import '@xterm/xterm/css/xterm.css'

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
      } catch {}
    }
  }, [terminalId])

  useEffect(() => {
    if (!containerRef.current) return

    let active = true
    let ptyReady = false

    const term = new Terminal({
      theme: {
        background: '#1a1a2e',
        foreground: '#0f0',
        cursor: '#0f0',
        selectionBackground: '#0f3460',
        black: '#1a1a2e',
        red: '#e74c3c',
        green: '#0f0',
        yellow: '#f1c40f',
        blue: '#3498db',
        magenta: '#9b59b6',
        cyan: '#1abc9c',
        white: '#ecf0f1',
        brightBlack: '#7f8c8d',
        brightRed: '#e74c3c',
        brightGreen: '#2ecc71',
        brightYellow: '#f1c40f',
        brightBlue: '#3498db',
        brightMagenta: '#9b59b6',
        brightCyan: '#1abc9c',
        brightWhite: '#ecf0f1',
      },
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

    const unsubData = terminalIpc.onData((id, data) => {
      if (id === terminalId && active) {
        term.write(data)
      }
    })

    const unsubExit = terminalIpc.onExit((id, exitCode) => {
      if (id === terminalId && active && ptyReady) {
        term.writeln(`\r\n\x1b[33m进程已退出 (code=${exitCode})\x1b[0m`)
        markExited(terminalId)
      }
    })

    term.onData((data) => {
      if (active) {
        terminalIpc.write(terminalId, data)
      }
    })

    terminalIpc.create(terminalId, cwd).then(({ pid }) => {
      if (active) {
        setPtyPid(terminalId, pid)
        ptyReady = true
      }
    }).catch((err) => {
      if (active) {
        term.writeln(`\x1b[31m终端创建失败: ${err.message}\x1b[0m`)
      }
    })

    const resizeObserver = new ResizeObserver(() => {
      handleResize()
    })
    resizeObserver.observe(containerRef.current)

    return () => {
      active = false
      ptyReady = false
      resizeObserver.disconnect()
      unsubData()
      unsubExit()
      terminalIpc.kill(terminalId)
      term.dispose()
      termRef.current = null
      fitAddonRef.current = null
    }
  }, [terminalId])

  return (
    <div ref={containerRef} className="h-full w-full" />
  )
}
