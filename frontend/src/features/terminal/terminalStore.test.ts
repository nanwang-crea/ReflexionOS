import { beforeEach, describe, expect, it } from 'vitest'
import { useTerminalStore, _resetForTesting } from './terminalStore'

beforeEach(() => {
  _resetForTesting()
})

describe('terminalStore', () => {
  it('should initialize with no terminals and panel hidden', () => {
    const state = useTerminalStore.getState()
    expect(state.instances).toEqual([])
    expect(state.activeTerminalId).toBeNull()
    expect(state.panelVisible).toBe(false)
    expect(state.panelHeight).toBe(200)
  })

  it('should create a terminal instance', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    const state = useTerminalStore.getState()
    expect(state.instances).toHaveLength(1)
    expect(state.instances[0].title).toBe('终端 1')
    expect(state.activeTerminalId).toBe(state.instances[0].id)
    expect(state.panelVisible).toBe(true)
    useTerminalStore.getState().closeTerminal(state.instances[0].id)
  })

  it('should create multiple terminals with sequential titles', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    useTerminalStore.getState().createTerminal('/test/project')
    const state = useTerminalStore.getState()
    expect(state.instances).toHaveLength(2)
    expect(state.instances[0].title).toBe('终端 1')
    expect(state.instances[1].title).toBe('终端 2')
    expect(state.activeTerminalId).toBe(state.instances[1].id)
    state.instances.forEach((t) => useTerminalStore.getState().closeTerminal(t.id))
  })

  it('should close a terminal and update active terminal', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    useTerminalStore.getState().createTerminal('/test/project')
    const { instances } = useTerminalStore.getState()
    const firstId = instances[0].id
    const secondId = instances[1].id
    useTerminalStore.getState().closeTerminal(firstId)
    const state = useTerminalStore.getState()
    expect(state.instances).toHaveLength(1)
    expect(state.instances[0].id).toBe(secondId)
    expect(state.activeTerminalId).toBe(secondId)
    useTerminalStore.getState().closeTerminal(secondId)
  })

  it('should close last terminal and hide panel', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    const { instances } = useTerminalStore.getState()
    useTerminalStore.getState().closeTerminal(instances[0].id)
    const state = useTerminalStore.getState()
    expect(state.instances).toHaveLength(0)
    expect(state.panelVisible).toBe(false)
  })

  it('should toggle panel visibility', () => {
    useTerminalStore.getState().togglePanel()
    expect(useTerminalStore.getState().panelVisible).toBe(true)
    useTerminalStore.getState().togglePanel()
    expect(useTerminalStore.getState().panelVisible).toBe(false)
  })

  it('should set panel height within bounds', () => {
    useTerminalStore.getState().setPanelHeight(300)
    expect(useTerminalStore.getState().panelHeight).toBe(300)
    useTerminalStore.getState().setPanelHeight(50)
    expect(useTerminalStore.getState().panelHeight).toBe(100)
    useTerminalStore.getState().setPanelHeight(9999)
    expect(useTerminalStore.getState().panelHeight).toBe(600)
  })

  it('should set active terminal', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    useTerminalStore.getState().createTerminal('/test/project')
    const { instances } = useTerminalStore.getState()
    useTerminalStore.getState().setActiveTerminal(instances[0].id)
    expect(useTerminalStore.getState().activeTerminalId).toBe(instances[0].id)
    instances.forEach((t) => useTerminalStore.getState().closeTerminal(t.id))
  })

  it('should mark terminal as exited', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    const { instances } = useTerminalStore.getState()
    useTerminalStore.getState().markExited(instances[0].id)
    expect(useTerminalStore.getState().instances[0].exited).toBe(true)
    useTerminalStore.getState().closeTerminal(instances[0].id)
  })

  it('should close all terminals', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    useTerminalStore.getState().createTerminal('/test/project')
    useTerminalStore.getState().closeAllTerminals()
    expect(useTerminalStore.getState().instances).toHaveLength(0)
    expect(useTerminalStore.getState().activeTerminalId).toBeNull()
    expect(useTerminalStore.getState().panelVisible).toBe(false)
  })
})
