import { readFileSync } from 'node:fs'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const DEFAULT_URL = 'http://localhost/'

function createStorage() {
  const storage = new Map<string, string>()

  return {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      storage.set(key, value)
    },
    removeItem: (key: string) => {
      storage.delete(key)
    },
    clear: () => {
      storage.clear()
    },
  }
}

function createWindow(search = '') {
  const location = {
    href: `${DEFAULT_URL}${search}`,
    search,
  }

  return {
    location,
    history: {
      replaceState: (_state: unknown, _title: string, url: string) => {
        const nextUrl = new URL(url, DEFAULT_URL)
        location.href = nextUrl.href
        location.search = nextUrl.search
      },
    },
  }
}

function setUrl(search = '') {
  window.history.replaceState({}, '', `${DEFAULT_URL}${search}`)
}

async function loadWorkspaceStore() {
  const module = await import('@/stores/workspaceStore')
  return module.useWorkspaceStore
}

describe('App cleanup', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubGlobal('localStorage', createStorage())
    vi.stubGlobal('window', createWindow())
    localStorage.clear()
    setUrl()
  })

  afterEach(() => {
    localStorage.clear()
    setUrl()
    vi.unstubAllGlobals()
  })

  it('does not keep the legacy /projects route once sidebar project management is the primary path', () => {
    const appSource = readFileSync(
      path.resolve(__dirname, 'App.tsx'),
      'utf8'
    )

    expect(appSource.includes("path=\"/projects\"")).toBe(false)
  })

  it('persists only the workspace ui slice to storage', async () => {
    const useWorkspaceStore = await loadWorkspaceStore()

    useWorkspaceStore.getState().setCurrentSessionId('session-42')
    useWorkspaceStore.getState().setProjectExpanded('project-a', true)
    useWorkspaceStore.getState().toggleProjectShowAll('project-b')
    useWorkspaceStore.getState().setSearchQuery('needle')
    useWorkspaceStore.getState().setSearchOpen(true)

    const payload = JSON.parse(localStorage.getItem('reflexion-workspace') || 'null')

    expect(payload).not.toBeNull()
    expect(payload.state).toEqual({
      currentSessionId: 'session-42',
      expandedProjectIds: ['project-a'],
      expandedSessionProjectIds: ['project-b'],
      searchQuery: 'needle',
      searchOpen: true,
    })
    expect(payload.state).not.toHaveProperty('sessions')
    expect(payload.state).not.toHaveProperty('createSession')
  })

  it('does not expose local session persistence helpers or mixed session aliases', async () => {
    const useWorkspaceStore = await loadWorkspaceStore()
    const state = useWorkspaceStore.getState() as unknown as Record<string, unknown>
    const workspaceTypesSource = readFileSync(
      path.resolve(__dirname, 'types/workspace.ts'),
      'utf8'
    )

    expect(state.saveSessionRounds).toBeUndefined()
    expect(state.updateSessionTitle).toBeUndefined()
    expect(state.updateSessionPreferences).toBeUndefined()
    expect(workspaceTypesSource.includes('interface ChatSession')).toBe(false)
    expect(workspaceTypesSource.includes('recentRounds')).toBe(false)
  })

  it('ignores previously persisted demo workspace payload and uses deterministic demo ui seeding', async () => {
    localStorage.setItem('reflexion-workspace-demo', JSON.stringify({
      state: {
        currentSessionId: 'persisted-session',
        expandedProjectIds: ['persisted-project'],
        expandedSessionProjectIds: ['persisted-show-all'],
        searchQuery: 'persisted-query',
        searchOpen: true,
      },
      version: 0,
    }))
    setUrl('?demo=1')

    const { demoWorkspaceState } = await import('@/demo/demoData')
    const useWorkspaceStore = await loadWorkspaceStore()
    const state = useWorkspaceStore.getState()

    expect({
      currentSessionId: state.currentSessionId,
      expandedProjectIds: state.expandedProjectIds,
      expandedSessionProjectIds: state.expandedSessionProjectIds,
      searchQuery: state.searchQuery,
      searchOpen: state.searchOpen,
    }).toEqual(demoWorkspaceState)
  })
})
