import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useContextMenuStore } from '../contextMenu.store'

describe('contextMenuStore', () => {
  beforeEach(() => {
    useContextMenuStore.setState({ isOpen: false, x: 0, y: 0, items: [] })
  })

  it('open sets isOpen, coordinates, and items', () => {
    const onClick = vi.fn()
    useContextMenuStore.getState().open(120, 240, [{ label: '复制', onClick }])

    const state = useContextMenuStore.getState()
    expect(state.isOpen).toBe(true)
    expect(state.x).toBe(120)
    expect(state.y).toBe(240)
    expect(state.items).toHaveLength(1)
    expect(state.items[0].label).toBe('复制')
  })

  it('open overwrites a previously open menu (single instance)', () => {
    useContextMenuStore.getState().open(10, 10, [{ label: 'A', onClick: vi.fn() }])
    useContextMenuStore.getState().open(50, 60, [{ label: 'B', onClick: vi.fn() }])

    const state = useContextMenuStore.getState()
    expect(state.x).toBe(50)
    expect(state.y).toBe(60)
    expect(state.items[0].label).toBe('B')
  })

  it('close resets isOpen and clears items', () => {
    useContextMenuStore.getState().open(10, 10, [{ label: 'A', onClick: vi.fn() }])
    useContextMenuStore.getState().close()

    const state = useContextMenuStore.getState()
    expect(state.isOpen).toBe(false)
    expect(state.items).toEqual([])
  })
})
