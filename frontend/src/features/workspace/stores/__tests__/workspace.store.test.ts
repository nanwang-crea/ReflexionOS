import { beforeEach, describe, expect, it, vi } from 'vitest'

// node 测试环境没有 localStorage，store 用 persist + createJSONStorage(localStorage)。
// 这里提供一个最小内存版 localStorage，保证 store 能正常加载与读写。
function installMemoryLocalStorage() {
  const store = new Map<string, string>()
  const mock = {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => {
      store.set(key, value)
    },
    removeItem: (key: string) => {
      store.delete(key)
    },
    clear: () => {
      store.clear()
    },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size
    },
  }
  vi.stubGlobal('localStorage', mock)
  return store
}

describe('workspace.store 会话级状态', () => {
  beforeEach(() => {
    installMemoryLocalStorage()
    vi.resetModules()
  })

  it('markSessionSeen 只前进、不回退已读基线', async () => {
    const { useWorkspaceStore } = await import('../workspace.store')
    const { markSessionSeen } = useWorkspaceStore.getState()

    markSessionSeen('session-1', 5)
    expect(useWorkspaceStore.getState().lastSeenEventSeqBySessionId['session-1']).toBe(5)

    // 更小的值不应回退。
    markSessionSeen('session-1', 3)
    expect(useWorkspaceStore.getState().lastSeenEventSeqBySessionId['session-1']).toBe(5)

    // 更大的值前进。
    markSessionSeen('session-1', 8)
    expect(useWorkspaceStore.getState().lastSeenEventSeqBySessionId['session-1']).toBe(8)
  })

  it('markSessionSyncDegraded / clearSessionSyncHealth 正确设置与清除', async () => {
    const { useWorkspaceStore } = await import('../workspace.store')
    const { markSessionSyncDegraded, clearSessionSyncHealth } = useWorkspaceStore.getState()

    markSessionSyncDegraded('session-1')
    expect(useWorkspaceStore.getState().sessionSyncHealthBySessionId['session-1']).toBe('degraded')

    clearSessionSyncHealth('session-1')
    expect('session-1' in useWorkspaceStore.getState().sessionSyncHealthBySessionId).toBe(false)
  })

  it('clearSessionSyncHealth 对不存在的会话是幂等无副作用', async () => {
    const { useWorkspaceStore } = await import('../workspace.store')
    const before = useWorkspaceStore.getState().sessionSyncHealthBySessionId
    useWorkspaceStore.getState().clearSessionSyncHealth('not-there')
    // 引用不变，说明没有产生无谓的 state 更新。
    expect(useWorkspaceStore.getState().sessionSyncHealthBySessionId).toBe(before)
  })

  it('未读基线与同步健康均写入持久化（localStorage）', async () => {
    const { useWorkspaceStore } = await import('../workspace.store')
    useWorkspaceStore.getState().markSessionSeen('session-1', 7)
    useWorkspaceStore.getState().markSessionSyncDegraded('session-1')

    const persisted = JSON.parse(localStorage.getItem('reflexion-workspace') ?? '{}')
    expect(persisted.state.lastSeenEventSeqBySessionId['session-1']).toBe(7)
    expect(persisted.state.sessionSyncHealthBySessionId['session-1']).toBe('degraded')
  })
})
