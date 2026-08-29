// @vitest-environment happy-dom
/**
 * codeTab.store 单元测试：覆盖多文件管理、代码面板宽度 clamp、
 * localStorage 持久化和侧边栏触发 clamp 等核心行为。
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { useCodeTabStore } from '../stores/codeTab.store'

// 多文件管理相关测试：打开/关闭文件、切换视图模式、dirty 状态、面板开关与宽度 clamp
describe('codeTabStore multi-file', () => {
  beforeEach(() => {
    useCodeTabStore.setState({
      openFiles: [],
      activeFileId: null,
      codePanelOpen: false,
      codePanelWidth: 480,
      sidebarOpen: false,
      sidebarWidth: 240,
      expandedDirs: {},
      sidebarTab: 'files',
      activeFile: null,
    })
  })

  it('openFile adds a file and activates it', () => {
    const { openFile } = useCodeTabStore.getState()
    openFile('src/app.py', 'edit')
    const state = useCodeTabStore.getState()
    expect(state.openFiles).toHaveLength(1)
    expect(state.openFiles[0].path).toBe('src/app.py')
    expect(state.openFiles[0].viewMode).toBe('edit')
    expect(state.activeFileId).toBe(state.openFiles[0].id)
    expect(state.codePanelOpen).toBe(true)
  })

  it('openFile with diff viewMode', () => {
    const { openFile } = useCodeTabStore.getState()
    openFile('src/app.py', 'diff')
    const state = useCodeTabStore.getState()
    expect(state.openFiles[0].viewMode).toBe('diff')
  })

  it('openFile activates existing file without changing viewMode', () => {
    const { openFile } = useCodeTabStore.getState()
    openFile('src/app.py', 'edit')
    openFile('src/main.ts', 'diff')
    openFile('src/app.py', 'diff')
    const state = useCodeTabStore.getState()
    expect(state.openFiles).toHaveLength(2)
    const appFile = state.openFiles.find((f) => f.path === 'src/app.py')!
    expect(appFile.viewMode).toBe('edit')
    expect(state.activeFileId).toBe(appFile.id)
  })

  it('closeFile removes file and activates neighbor', () => {
    const { openFile, closeFile } = useCodeTabStore.getState()
    openFile('a.py', 'edit')
    openFile('b.py', 'edit')
    openFile('c.py', 'edit')
    const bId = useCodeTabStore.getState().openFiles.find((f) => f.path === 'b.py')!.id
    closeFile(bId)
    const state = useCodeTabStore.getState()
    expect(state.openFiles).toHaveLength(2)
    expect(state.activeFileId).not.toBe(bId)
  })

  it('closeFile on last file sets activeFileId to null', () => {
    const { openFile, closeFile } = useCodeTabStore.getState()
    openFile('a.py', 'edit')
    const id = useCodeTabStore.getState().openFiles[0].id
    closeFile(id)
    const state = useCodeTabStore.getState()
    expect(state.openFiles).toHaveLength(0)
    expect(state.activeFileId).toBeNull()
  })

  it('setViewMode changes viewMode for a specific file', () => {
    const { openFile, setViewMode } = useCodeTabStore.getState()
    openFile('a.py', 'edit')
    const id = useCodeTabStore.getState().openFiles[0].id
    setViewMode(id, 'diff')
    expect(useCodeTabStore.getState().openFiles[0].viewMode).toBe('diff')
  })

  it('setDirty updates dirty state and modifiedContent', () => {
    const { openFile, setDirty } = useCodeTabStore.getState()
    openFile('a.py', 'edit')
    const id = useCodeTabStore.getState().openFiles[0].id
    setDirty(id, true, 'new content')
    const f = useCodeTabStore.getState().openFiles[0]
    expect(f.isDirty).toBe(true)
    expect(f.modifiedContent).toBe('new content')
  })

  it('clearDirty resets dirty state', () => {
    const { openFile, setDirty, clearDirty } = useCodeTabStore.getState()
    openFile('a.py', 'edit')
    const id = useCodeTabStore.getState().openFiles[0].id
    setDirty(id, true, 'new content')
    clearDirty(id)
    const f = useCodeTabStore.getState().openFiles[0]
    expect(f.isDirty).toBe(false)
    expect(f.modifiedContent).toBeUndefined()
  })

  it('setFileLanguage updates language in OpenFile', () => {
    const { openFile, setFileLanguage } = useCodeTabStore.getState()
    openFile('a.py', 'edit')
    const id = useCodeTabStore.getState().openFiles[0].id
    setFileLanguage(id, 'python')
    expect(useCodeTabStore.getState().openFiles[0].language).toBe('python')
    expect(useCodeTabStore.getState().activeFile?.language).toBe('python')
  })

  it('activeFile helper returns the active OpenFile', () => {
    const { openFile } = useCodeTabStore.getState()
    openFile('a.py', 'edit')
    openFile('b.py', 'edit')
    const state = useCodeTabStore.getState()
    expect(state.activeFile?.path).toBe('b.py')
  })

  it('codePanelOpen defaults to false and toggles', () => {
    expect(useCodeTabStore.getState().codePanelOpen).toBe(false)
    useCodeTabStore.getState().toggleCodePanel()
    expect(useCodeTabStore.getState().codePanelOpen).toBe(true)
    useCodeTabStore.getState().toggleCodePanel()
    expect(useCodeTabStore.getState().codePanelOpen).toBe(false)
  })

  it('setCodePanelOpen sets an explicit value', () => {
    useCodeTabStore.getState().setCodePanelOpen(true)
    expect(useCodeTabStore.getState().codePanelOpen).toBe(true)
    useCodeTabStore.getState().setCodePanelOpen(false)
    expect(useCodeTabStore.getState().codePanelOpen).toBe(false)
  })

  it('setCodePanelWidth clamps to MIN_CODE_PANEL_WIDTH', () => {
    useCodeTabStore.getState().setCodePanelWidth(100)
    expect(useCodeTabStore.getState().codePanelWidth).toBe(320)
  })

  it('setCodePanelWidth clamps to effectiveMax based on window.innerWidth', () => {
    const original = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { value: 1220, configurable: true })
    useCodeTabStore.setState({ sidebarOpen: false })
    // effectiveMax = 1220 - 0 - 400 = 820
    useCodeTabStore.getState().setCodePanelWidth(9999)
    expect(useCodeTabStore.getState().codePanelWidth).toBe(820)
    Object.defineProperty(window, 'innerWidth', { value: original, configurable: true })
  })

  it('setCodePanelWidth accounts for sidebarWidth when sidebarOpen is true', () => {
    const original = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { value: 1220, configurable: true })
    useCodeTabStore.setState({ sidebarOpen: true, sidebarWidth: 480 })
    // effectiveMax = 1220 - 480 - 400 = 340
    useCodeTabStore.getState().setCodePanelWidth(9999)
    expect(useCodeTabStore.getState().codePanelWidth).toBe(340)
    Object.defineProperty(window, 'innerWidth', { value: original, configurable: true })
  })

  it('setCodePanelWidth within bounds is unchanged', () => {
    const original = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { value: 1600, configurable: true })
    useCodeTabStore.setState({ sidebarOpen: false })
    useCodeTabStore.getState().setCodePanelWidth(500)
    expect(useCodeTabStore.getState().codePanelWidth).toBe(500)
    Object.defineProperty(window, 'innerWidth', { value: original, configurable: true })
  })
})

// localStorage 持久化相关测试：验证只持久化 codePanelWidth，其余字段不落盘
describe('codeTabStore persistence', () => {
  beforeEach(() => {
    localStorage.clear()
    useCodeTabStore.setState({
      codePanelOpen: false,
      codePanelWidth: 480,
    })
  })

  it('persists only codePanelWidth to localStorage', () => {
    useCodeTabStore.getState().setCodePanelWidth(600)
    useCodeTabStore.getState().setCodePanelOpen(true)
    const raw = localStorage.getItem('reflexion-code-panel')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!)
    expect(parsed.state.codePanelWidth).toBe(600)
    expect(parsed.state.codePanelOpen).toBeUndefined()
    expect(parsed.state.openFiles).toBeUndefined()
  })
})

// 窗口 resize 触发的宽度 clamp 测试：窗口缩小后代码面板宽度应自动收敛
describe('codeTabStore window resize clamp', () => {
  beforeEach(() => {
    useCodeTabStore.setState({ codePanelWidth: 900, sidebarOpen: false, sidebarWidth: 240 })
  })

  it('clamps codePanelWidth when window shrinks below effectiveMax', () => {
    const original = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { value: 1220, configurable: true })
    window.dispatchEvent(new Event('resize'))
    // effectiveMax = 1220 - 0 - 400 = 820
    expect(useCodeTabStore.getState().codePanelWidth).toBe(820)
    Object.defineProperty(window, 'innerWidth', { value: original, configurable: true })
    window.dispatchEvent(new Event('resize'))
  })
})

// 侧边栏（文件树）展开/收起及宽度变化触发的代码面板宽度 clamp 测试
describe('codeTabStore sidebar-triggered clamp', () => {
  beforeEach(() => {
    const original = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { value: 1220, configurable: true })
    useCodeTabStore.setState({ codePanelWidth: 700, sidebarOpen: false, sidebarWidth: 240 })
    ;(globalThis as { __restoreInnerWidth?: () => void }).__restoreInnerWidth = () => {
      Object.defineProperty(window, 'innerWidth', { value: original, configurable: true })
    }
  })

  it('setSidebarOpen(true) re-clamps codePanelWidth using current sidebarWidth', () => {
    useCodeTabStore.setState({ sidebarWidth: 480 })
    useCodeTabStore.getState().setSidebarOpen(true)
    // effectiveMax = 1220 - 480 - 400 = 340
    expect(useCodeTabStore.getState().codePanelWidth).toBe(340)
  })

  it('setSidebarWidth while sidebarOpen re-clamps codePanelWidth', () => {
    useCodeTabStore.getState().setSidebarOpen(true)
    useCodeTabStore.setState({ codePanelWidth: 700 })
    useCodeTabStore.getState().setSidebarWidth(480)
    // effectiveMax = 1220 - 480 - 400 = 340
    expect(useCodeTabStore.getState().codePanelWidth).toBe(340)
  })

  it('setSidebarOpen(false) does not shrink codePanelWidth unnecessarily', () => {
    useCodeTabStore.setState({ codePanelWidth: 700, sidebarOpen: true, sidebarWidth: 480 })
    useCodeTabStore.getState().setSidebarOpen(false)
    // effectiveMax = 1220 - 0 - 400 = 820, 700 已经在范围内，不应被压缩
    expect(useCodeTabStore.getState().codePanelWidth).toBe(700)
  })
})
