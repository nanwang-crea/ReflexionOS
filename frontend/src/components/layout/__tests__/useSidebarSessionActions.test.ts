// useSidebarSessionActions 的单测：mock 会话相关 action 函数（创建/重命名/删除），
// 验证创建失败时通过 dialogService 报告错误，以及重命名会话时正确传递新标题。
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSidebarSessionActions } from '../useSidebarSessionActions'
import type { Project } from '@/types/project'
import type { DialogService } from '@/services/dialogService'

// 参数：id - 项目 id。
// 作用：构造一个最小 Project 测试夹具，name/path 均基于 id 生成。
// 返回：完整的 Project 对象。
function createProject(id: string): Project {
  return {
    id,
    name: id,
    path: `/tmp/${id}`,
    language: 'typescript',
    created_at: '2026-04-19T00:00:00.000Z',
    updated_at: '2026-04-19T00:00:00.000Z',
  }
}

// 参数：overrides - 需要覆盖的 DialogService 方法。
// 作用：构造一个带默认 mock 实现的 DialogService。
// 返回：完整的 DialogService 对象。
function createDialogService(overrides: Partial<DialogService> = {}): DialogService {
  return {
    notifyError: vi.fn(),
    confirmAction: vi.fn(async () => true),
    promptText: vi.fn(() => null),
    ...overrides,
  }
}

// 用 vi.hoisted 预先声明 mock 函数，供下方 vi.mock 工厂函数引用。
const {
  createSessionMock,
  updateSessionMock,
  deleteSessionMock,
} = vi.hoisted(() => ({
  createSessionMock: vi.fn(),
  updateSessionMock: vi.fn(),
  deleteSessionMock: vi.fn(),
}))

// mock 会话 action 模块：create/rename/delete 替换为可控的 mock 函数。
vi.mock('@/features/sessions/session.actions', () => ({
  createSession: createSessionMock,
  renameSession: updateSessionMock,
  deleteSession: deleteSessionMock,
}))

describe('useSidebarSessionActions', () => {
  // 每个用例执行前重置所有 mock 的调用记录/实现，避免用例间相互污染。
  beforeEach(() => {
    createSessionMock.mockReset()
    updateSessionMock.mockReset()
    deleteSessionMock.mockReset()
  })

  // 参数：无。
  // 验证：创建会话 action 调用失败（reject）时，通过 dialogService.notifyError 提示“创建聊天失败”。
  it('reports session action failures through the dialog service', async () => {
    createSessionMock.mockRejectedValue(new Error('boom'))
    const dialogService = createDialogService()
    const actions = useSidebarSessionActions({
      busy: false,
      projects: [createProject('project-1')],
      currentProject: createProject('project-1'),
      currentSessionId: null,
      setCurrentProject: vi.fn(),
      setProjectExpanded: vi.fn(),
      setCurrentSessionId: vi.fn(),
      setShowProjectModal: vi.fn(),
      navigate: vi.fn(),
      dialogService,
    })

    await actions.handleCreateSession()

    expect(dialogService.notifyError).toHaveBeenCalledWith('创建聊天失败')
  })

  // 参数：无。
  // 验证：重命名会话时，以指定的新标题调用底层 renameSession（updateSessionMock）。
  it('renames session with provided title', async () => {
    updateSessionMock.mockResolvedValue(undefined)
    const dialogService = createDialogService()
    const actions = useSidebarSessionActions({
      busy: false,
      projects: [createProject('project-1')],
      currentProject: createProject('project-1'),
      currentSessionId: 'session-1',
      setCurrentProject: vi.fn(),
      setProjectExpanded: vi.fn(),
      setCurrentSessionId: vi.fn(),
      setShowProjectModal: vi.fn(),
      navigate: vi.fn(),
      dialogService,
    })

    await actions.handleRenameSession('session-1', '新的标题')

    expect(updateSessionMock).toHaveBeenCalledWith('session-1', '新的标题')
  })
})
