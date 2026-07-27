/**
 * 代码面板 Zustand Store：管理代码面板（右侧侧边栏）的开关状态、宽度、
 * 已打开文件列表、文件树侧边栏状态、以及目录展开状态。
 * 宽度变更时统一经过 clampCodePanelWidth 约束，防止挤压对话区到最小宽度以下。
 * codePanelWidth 持久化到 localStorage；codePanelOpen 不持久化（每次启动固定收起）。
 */

import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type ViewMode = 'edit' | 'diff'

export interface OpenFile {
  id: string
  path: string
  language: string
  isDirty: boolean
  viewMode: ViewMode
  modifiedContent?: string
  originalContent?: string
}

// 文件树侧边栏宽度边界
const MIN_SIDEBAR_WIDTH = 180
const MAX_SIDEBAR_WIDTH = 480
const DEFAULT_SIDEBAR_WIDTH = 240

// 代码面板宽度边界：MIN_CODE_PANEL + MIN_CHAT = 代码面板和对话区的最低保证宽度之和
const MIN_CODE_PANEL_WIDTH = 320
const MIN_CHAT_WIDTH = 400
const DEFAULT_CODE_PANEL_WIDTH = 480

// 文件 id 计数器（模块级，避免 id 碰撞，不需要持久化）
let _nextFileId = 0

interface CodeTabState {
  codePanelOpen: boolean
  codePanelWidth: number
  openFiles: OpenFile[]
  activeFileId: string | null
  sidebarOpen: boolean
  sidebarWidth: number
  expandedDirs: Record<string, boolean>
  sidebarTab: 'files' | 'changes'
  activeFile: OpenFile | null
  fileTreeVersion: number
}

interface CodeTabActions {
  setCodePanelOpen: (open: boolean) => void
  toggleCodePanel: () => void
  setCodePanelWidth: (width: number) => void
  openFile: (path: string, viewMode: ViewMode) => void
  closeFile: (id: string) => void
  setViewMode: (id: string, mode: ViewMode) => void
  setDirty: (id: string, isDirty: boolean, modifiedContent?: string) => void
  clearDirty: (id: string) => void
  setFileLanguage: (id: string, language: string) => void
  setActiveFile: (path: string, language: string) => void
  setSidebarOpen: (open: boolean) => void
  toggleSidebar: () => void
  setSidebarWidth: (width: number) => void
  toggleDir: (path: string) => void
  setDirExpanded: (path: string, expanded: boolean) => void
  setSidebarTab: (tab: 'files' | 'changes') => void
  refreshFileTree: () => void
}

export { MIN_SIDEBAR_WIDTH, MAX_SIDEBAR_WIDTH, MIN_CODE_PANEL_WIDTH, MIN_CHAT_WIDTH }

/**
 * 计算 codePanelWidth 的合法范围并 clamp。
 * effectiveMax = 可视区宽度 - (文件树宽度，若侧边栏展开) - 对话区最小宽度
 * 保证代码面板不会超出可用空间，也不会小于最小宽度。
 * 输入：requestedWidth（目标宽度）、sidebarOpen（文件树是否展开）、sidebarWidth（文件树当前宽度）
 * 输出：clamp 后的合法宽度
 */
function clampCodePanelWidth(requestedWidth: number, sidebarOpen: boolean, sidebarWidth: number): number {
  const effectiveMax = window.innerWidth - (sidebarOpen ? sidebarWidth : 0) - MIN_CHAT_WIDTH
  return Math.max(MIN_CODE_PANEL_WIDTH, Math.min(effectiveMax, requestedWidth))
}

export const useCodeTabStore = create<CodeTabState & CodeTabActions>()(
  persist(
    (set) => ({
      codePanelOpen: false,
      codePanelWidth: DEFAULT_CODE_PANEL_WIDTH,
      openFiles: [],
      activeFileId: null,
      sidebarOpen: false,
      sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
      expandedDirs: {},
      sidebarTab: 'files' as const,
      activeFile: null,
      fileTreeVersion: 0,

      /** 直接设置代码面板开关状态 */
      setCodePanelOpen: (open) => set({ codePanelOpen: open }),

      /** 切换代码面板开关 */
      toggleCodePanel: () => set((state) => ({ codePanelOpen: !state.codePanelOpen })),

      /**
       * 设置代码面板宽度，自动 clamp 到合法范围。
       * 拖拽调宽、窗口 resize、rehydrate、sidebarOpen 变化时均应调用此方法。
       */
      setCodePanelWidth: (width) =>
        set((state) => ({
          codePanelWidth: clampCodePanelWidth(width, state.sidebarOpen, state.sidebarWidth),
        })),

      /**
       * 打开文件：若文件已在 openFiles 中，直接激活；否则新建并追加。
       * 同时展开代码面板（让用户能看到刚打开的文件）。
       * 输入：path（文件路径）、viewMode（'edit' 或 'diff'）
       */
      openFile: (path, viewMode) =>
        set((state) => {
          const existing = state.openFiles.find((f) => f.path === path)
          if (existing) {
            return {
              activeFileId: existing.id,
              codePanelOpen: true,
              activeFile: existing,
            }
          }
          const newFile: OpenFile = {
            id: `file-${++_nextFileId}`,
            path,
            language: '',
            isDirty: false,
            viewMode,
          }
          const nextFiles = [...state.openFiles, newFile]
          return {
            openFiles: nextFiles,
            activeFileId: newFile.id,
            codePanelOpen: true,
            activeFile: newFile,
          }
        }),

      /**
       * 关闭文件 tab：移除文件，并自动激活相邻文件（优先右侧，无则左侧）。
       * 输入：id（文件 id）
       */
      closeFile: (id) =>
        set((state) => {
          const idx = state.openFiles.findIndex((f) => f.id === id)
          if (idx === -1) return state
          const nextFiles = state.openFiles.filter((f) => f.id !== id)
          let nextActiveId: string | null = null
          if (state.activeFileId === id) {
            if (nextFiles.length === 0) {
              nextActiveId = null
            } else if (idx < nextFiles.length) {
              nextActiveId = nextFiles[idx].id
            } else {
              nextActiveId = nextFiles[nextFiles.length - 1].id
            }
          } else {
            nextActiveId = state.activeFileId
          }
          const nextActive = nextActiveId
            ? nextFiles.find((f) => f.id === nextActiveId) ?? null
            : null
          return {
            openFiles: nextFiles,
            activeFileId: nextActiveId,
            activeFile: nextActive,
          }
        }),

      /**
       * 切换指定文件的视图模式（edit/diff）。
       * 输入：id（文件 id）、mode（目标视图模式）
       */
      setViewMode: (id, mode) =>
        set((state) => {
          const nextFiles = state.openFiles.map((f) =>
            f.id === id ? { ...f, viewMode: mode } : f,
          )
          const nextActive = state.activeFileId === id
            ? { ...state.activeFile!, viewMode: mode }
            : state.activeFile
          return { openFiles: nextFiles, activeFile: nextActive }
        }),

      /**
       * 标记文件为 dirty（有未保存修改），同步 modifiedContent。
       * 输入：id、isDirty、modifiedContent（可选，编辑后的内容）
       */
      setDirty: (id, isDirty, modifiedContent) =>
        set((state) => {
          const nextFiles = state.openFiles.map((f) =>
            f.id === id ? { ...f, isDirty, modifiedContent } : f,
          )
          const nextActive = state.activeFileId === id
            ? { ...state.activeFile!, isDirty, modifiedContent }
            : state.activeFile
          return { openFiles: nextFiles, activeFile: nextActive }
        }),

      /**
       * 清除文件的 dirty 状态（保存后调用）。
       * 输入：id（文件 id）
       */
      clearDirty: (id) =>
        set((state) => {
          const nextFiles = state.openFiles.map((f) =>
            f.id === id ? { ...f, isDirty: false, modifiedContent: undefined } : f,
          )
          const nextActive = state.activeFileId === id
            ? { ...state.activeFile!, isDirty: false, modifiedContent: undefined }
            : state.activeFile
          return { openFiles: nextFiles, activeFile: nextActive }
        }),

      /**
       * 更新文件的语言标识（由编辑器检测后回填）。
       * 输入：id（文件 id）、language（语言字符串，如 'python'）
       */
      setFileLanguage: (id, language) =>
        set((state) => {
          const nextFiles = state.openFiles.map((f) =>
            f.id === id ? { ...f, language } : f,
          )
          const nextActive = state.activeFileId === id
            ? { ...state.activeFile!, language }
            : state.activeFile
          return { openFiles: nextFiles, activeFile: nextActive }
        }),

      /**
       * 激活指定路径的文件（若不存在则新建），与 openFile 的区别是会接收 language 参数。
       * 通常由外部（如文件树点击）调用。
       * 输入：path（文件路径）、language（语言标识）
       */
      setActiveFile: (path, language) => {
        const state = useCodeTabStore.getState()
        const existing = state.openFiles.find((f) => f.path === path)
        if (existing) {
          set({
            activeFileId: existing.id,
            codePanelOpen: true,
            activeFile: existing,
          })
        } else {
          const newFile: OpenFile = {
            id: `file-${++_nextFileId}`,
            path,
            language,
            isDirty: false,
            viewMode: 'edit',
          }
          set({
            openFiles: [...state.openFiles, newFile],
            activeFileId: newFile.id,
            codePanelOpen: true,
            activeFile: newFile,
          })
        }
      },

      /**
       * 设置文件树侧边栏开关，同时 re-clamp codePanelWidth（侧边栏宽度变化会影响代码面板上限）。
       * 输入：open（是否展开）
       */
      setSidebarOpen: (open) =>
        set((state) => ({
          sidebarOpen: open,
          codePanelWidth: clampCodePanelWidth(state.codePanelWidth, open, state.sidebarWidth),
        })),

      /** 切换文件树侧边栏开关，同时 re-clamp codePanelWidth */
      toggleSidebar: () =>
        set((state) => {
          const nextOpen = !state.sidebarOpen
          return {
            sidebarOpen: nextOpen,
            codePanelWidth: clampCodePanelWidth(state.codePanelWidth, nextOpen, state.sidebarWidth),
          }
        }),

      /**
       * 设置文件树侧边栏宽度（拖拽调宽时调用），同时 re-clamp codePanelWidth。
       * 输入：width（目标宽度，会被 clamp 到 [MIN_SIDEBAR_WIDTH, MAX_SIDEBAR_WIDTH]）
       */
      setSidebarWidth: (width) =>
        set((state) => {
          const nextSidebarWidth = Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, width))
          return {
            sidebarWidth: nextSidebarWidth,
            codePanelWidth: clampCodePanelWidth(state.codePanelWidth, state.sidebarOpen, nextSidebarWidth),
          }
        }),

      /** 切换目录展开/折叠状态 */
      toggleDir: (path) =>
        set((state) => ({
          expandedDirs: { ...state.expandedDirs, [path]: !state.expandedDirs[path] },
        })),

      /** 显式设置目录展开/折叠状态 */
      setDirExpanded: (path, expanded) =>
        set((state) => ({
          expandedDirs: { ...state.expandedDirs, [path]: expanded },
        })),

      /** 切换侧边栏 tab（files/changes） */
      setSidebarTab: (tab) => set({ sidebarTab: tab }),

      /** 递增 fileTreeVersion，触发文件树重新加载（如文件系统变化后调用） */
      refreshFileTree: () => set((s) => ({ fileTreeVersion: s.fileTreeVersion + 1 })),
    }),
    {
      name: 'reflexion-code-panel',
      storage: createJSONStorage(() => localStorage),
      // 只持久化宽度；codePanelOpen 不持久化（每次启动固定收起）
      partialize: (state) => ({
        codePanelWidth: state.codePanelWidth,
      }),
      // rehydrate 后对宽度执行一次 clamp（窗口大小可能在上次退出后变化）
      onRehydrateStorage: () => (state) => {
        if (!state) return
        state.setCodePanelWidth(state.codePanelWidth)
      },
    },
  ),
)

// 窗口缩小时自动收敛 codePanelWidth（模块级副作用，随模块加载注册一次）
if (typeof window !== 'undefined') {
  window.addEventListener('resize', () => {
    const { codePanelWidth, setCodePanelWidth } = useCodeTabStore.getState()
    setCodePanelWidth(codePanelWidth)
  })
}
