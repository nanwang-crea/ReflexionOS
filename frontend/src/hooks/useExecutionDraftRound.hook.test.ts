import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('useExecutionDraftRound', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('returns the latest draft item count even when using a stale callback reference', async () => {
    const stateSlots: unknown[] = []
    const refSlots: Array<{ current: unknown }> = []
    let stateCursor = 0
    let refCursor = 0

    vi.doMock('react', () => ({
      useState: <T,>(initialValue: T) => {
        const slot = stateCursor++
        if (!(slot in stateSlots)) {
          stateSlots[slot] = initialValue
        }

        const snapshot = stateSlots[slot] as T
        const setState = (value: T | ((current: T) => T)) => {
          stateSlots[slot] = typeof value === 'function'
            ? (value as (current: T) => T)(stateSlots[slot] as T)
            : value
        }

        return [snapshot, setState] as const
      },
      useRef: <T,>(initialValue: T) => {
        const slot = refCursor++
        if (!(slot in refSlots)) {
          refSlots[slot] = { current: initialValue }
        }

        return refSlots[slot] as { current: T }
      },
      useCallback: <T extends (...args: never[]) => unknown>(callback: T) => callback,
    }))

    const { useExecutionDraftRound } = await import('./useExecutionDraftRound')

    stateCursor = 0
    refCursor = 0
    const firstRender = useExecutionDraftRound()

    firstRender.startDraftRound('session-1', 'hello')

    stateCursor = 0
    refCursor = 0
    const secondRender = useExecutionDraftRound()

    secondRender.appendItems([
      {
        id: 'assistant-1',
        type: 'assistant-message',
        content: 'hi there',
      },
    ])

    expect(firstRender.getItemCount()).toBe(2)
  })

  it('tracks assistant items appended after a later render before the draft is cleared', async () => {
    const stateSlots: unknown[] = []
    const refSlots: Array<{ current: unknown }> = []
    const pendingStateUpdates: Array<() => void> = []
    let stateCursor = 0
    let refCursor = 0

    vi.doMock('react', () => ({
      useState: <T,>(initialValue: T) => {
        const slot = stateCursor++
        if (!(slot in stateSlots)) {
          stateSlots[slot] = initialValue
        }

        const snapshot = stateSlots[slot] as T
        const setState = (value: T | ((current: T) => T)) => {
          pendingStateUpdates.push(() => {
            stateSlots[slot] = typeof value === 'function'
              ? (value as (current: T) => T)(stateSlots[slot] as T)
              : value
          })
        }

        return [snapshot, setState] as const
      },
      useRef: <T,>(initialValue: T) => {
        const slot = refCursor++
        if (!(slot in refSlots)) {
          refSlots[slot] = { current: initialValue }
        }

        return refSlots[slot] as { current: T }
      },
      useCallback: <T extends (...args: never[]) => unknown>(callback: T) => callback,
    }))

    const { useExecutionDraftRound } = await import('./useExecutionDraftRound')

    stateCursor = 0
    refCursor = 0
    const renderA = useExecutionDraftRound()
    renderA.startDraftRound('session-1', 'hello')

    stateCursor = 0
    refCursor = 0
    const renderB = useExecutionDraftRound()
    renderB.appendItems([
      {
        id: 'assistant-1',
        type: 'assistant-message',
        content: 'hi there',
      },
    ])

    stateCursor = 0
    refCursor = 0
    const renderC = useExecutionDraftRound()

    pendingStateUpdates.forEach((applyUpdate) => applyUpdate())

    expect(renderC.getItemCount()).toBe(2)
  })
})
