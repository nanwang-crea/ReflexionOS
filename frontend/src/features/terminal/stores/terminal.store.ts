/**
 * 文件功能：终端面板 Zustand Store
 * 文件描述：管理多终端实例（instances）、当前激活终端、终端面板显示状态与高度。
 * panelVisible 和 panelHeight 持久化到 localStorage；具体终端实例（instances）不持久化
 * （因为 pty 进程随应用退出而结束，重启后无法恢复）。
 * 核心逻辑：createTerminal 创建新终端并自动激活、展开面板；closeTerminal 结束时通知后端
 * kill 对应 pty 进程，并在关闭当前激活终端时自动切换到相邻终端；面板高度统一经 clamp 约束。
 */

import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { terminalIpc } from '@/services/terminalIpc'

const MIN_PANEL_HEIGHT = 100
const MAX_PANEL_HEIGHT = 600
const DEFAULT_PANEL_HEIGHT = 280

/** 单个终端实例：id（唯一标识）、title（展示标题，如"终端 1"）、ptyPid（对应 pty 进程号）、exited（是否已退出）、cwd（工作目录） */
export interface TerminalInstance {
  id: string
  title: string
  ptyPid: number | null
  exited: boolean
  cwd: string
}

interface TerminalState {
  instances: TerminalInstance[]
  activeTerminalId: string | null
  panelVisible: boolean
  panelHeight: number
}

interface TerminalActions {
  createTerminal: (cwd: string) => string
  closeTerminal: (id: string) => void
  closeAllTerminals: () => void
  setActiveTerminal: (id: string) => void
  setPtyPid: (id: string, pid: number) => void
  togglePanel: () => void
  setPanelVisible: (visible: boolean) => void
  setPanelHeight: (height: number) => void
  markExited: (id: string) => void
}

// 终端标题计数器（模块级，用于生成"终端 1"、"终端 2"等递增标题，不需要持久化）
export let terminalCounter = 0

/**
 * 函数名：_resetForTesting
 * 入参：无
 * 功能：仅供单元测试使用，重置终端计数器与 store 状态到初始值
 * 运行逻辑：将 terminalCounter 归零，并将 store 的 instances/activeTerminalId/panelVisible/panelHeight
 * 重置为默认状态，避免测试用例之间互相污染
 * 出参：无
 */
export function _resetForTesting() {
  terminalCounter = 0
  useTerminalStore.setState({
    instances: [],
    activeTerminalId: null,
    panelVisible: false,
    panelHeight: DEFAULT_PANEL_HEIGHT,
  })
}

export const useTerminalStore = create<TerminalState & TerminalActions>()(
  persist(
    (set) => ({
      instances: [],
      activeTerminalId: null,
      panelVisible: false,
      panelHeight: DEFAULT_PANEL_HEIGHT,

      /**
       * 创建新终端实例。入参：cwd（终端的初始工作目录）
       * 运行逻辑：递增 terminalCounter 生成唯一 id 和标题（"终端 N"），追加到 instances，
       * 自动激活该终端并展开面板（panelVisible=true）
       * 出参：string - 新建终端的 id
       */
      createTerminal: (cwd: string) => {
        terminalCounter += 1
        const id = `term-${Date.now()}-${terminalCounter}`
        const instance: TerminalInstance = {
          id,
          title: `终端 ${terminalCounter}`,
          ptyPid: null,
          exited: false,
          cwd,
        }
        set((state) => ({
          instances: [...state.instances, instance],
          activeTerminalId: id,
          panelVisible: true,
        }))
        return id
      },

      /**
       * 关闭指定终端。入参：id（终端 id）
       * 运行逻辑：调用 terminalIpc.kill 结束对应 pty 进程（失败静默忽略）；
       * 从 instances 中移除该终端；若关闭的正是当前激活终端，则激活剩余列表中最后一个终端，
       * 若无剩余终端则将 activeTerminalId 置空；若所有终端都已关闭则同时隐藏面板
       */
      closeTerminal: (id) => {
        terminalIpc.kill(id).catch(() => {})
        set((state) => {
          const remaining = state.instances.filter((t) => t.id !== id)
          let newActiveId = state.activeTerminalId
          if (newActiveId === id) {
            newActiveId = remaining.length > 0 ? remaining[remaining.length - 1].id : null
          }
          return {
            instances: remaining,
            activeTerminalId: newActiveId,
            panelVisible: remaining.length > 0 ? state.panelVisible : false,
          }
        })
      },

      /**
       * 关闭所有终端。入参：无
       * 运行逻辑：遍历当前所有终端实例逐个调用 terminalIpc.kill 结束进程（失败静默忽略），
       * 然后清空 instances、activeTerminalId 并隐藏面板
       */
      closeAllTerminals: () => {
        const { instances } = useTerminalStore.getState()
        for (const inst of instances) {
          terminalIpc.kill(inst.id).catch(() => {})
        }
        set({ instances: [], activeTerminalId: null, panelVisible: false })
      },

      /** 设置当前激活终端。入参：id（终端 id） */
      setActiveTerminal: (id) => set({ activeTerminalId: id }),

      /** 回填终端对应的 pty 进程号（pty 创建成功后由外部调用）。入参：id（终端 id）、pid（pty 进程号） */
      setPtyPid: (id, pid) =>
        set((state) => ({
          instances: state.instances.map((t) =>
            t.id === id ? { ...t, ptyPid: pid } : t,
          ),
        })),

      /** 切换终端面板显示/隐藏状态 */
      togglePanel: () =>
        set((state) => ({ panelVisible: !state.panelVisible })),

      /** 显式设置终端面板显示/隐藏状态。入参：visible */
      setPanelVisible: (visible) => set({ panelVisible: visible }),

      /** 设置终端面板高度，自动 clamp 到 [MIN_PANEL_HEIGHT, MAX_PANEL_HEIGHT] 范围内。入参：height（目标高度） */
      setPanelHeight: (height) =>
        set({
          panelHeight: Math.max(MIN_PANEL_HEIGHT, Math.min(MAX_PANEL_HEIGHT, height)),
        }),

      /** 标记终端为已退出状态（pty 进程退出后由外部调用，用于 UI 区分已结束的终端）。入参：id（终端 id） */
      markExited: (id) =>
        set((state) => ({
          instances: state.instances.map((t) =>
            t.id === id ? { ...t, exited: true } : t,
          ),
        })),
    }),
    {
      name: 'reflexion-terminal',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        panelVisible: state.panelVisible,
        panelHeight: state.panelHeight,
      }),
    },
  ),
)
