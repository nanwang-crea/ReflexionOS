import { beforeEach, describe, expect, it } from 'vitest'
import { useCodeTabStore } from './codeTabStore'

describe('codeTabStore multi-file', () => {
  beforeEach(() => {
    useCodeTabStore.setState({
      openFiles: [],
      activeFileId: null,
      workspaceTab: 'chat',
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
    expect(state.workspaceTab).toBe('code')
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
})
