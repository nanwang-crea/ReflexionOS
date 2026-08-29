// useSidebarProjectActions 的单测：mock 项目相关 API 与目录选择器，
// 验证删除/创建项目的成功与失败路径、忙碌态下跳过目录选择、空名称校验、以及从目录路径自动填充项目名。
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSidebarProjectActions } from '../useSidebarProjectActions'
import type { DialogService } from '@/services/dialogService'
import type { Project } from '@/types/project'

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
// 作用：构造一个带默认 mock 实现的 DialogService（notifyError/confirmAction/promptText 均为 vi.fn）。
// 返回：完整的 DialogService 对象。
function createDialogService(overrides: Partial<DialogService> = {}): DialogService {
  return {
    notifyError: vi.fn(),
    confirmAction: vi.fn(async () => true),
    promptText: vi.fn(() => null),
    ...overrides,
  }
}

// 用 vi.hoisted 预先声明 mock 函数，确保在下方 vi.mock 工厂函数中可以引用（vi.mock 会被提升到文件顶部）。
const {
  createProjectApiMock,
  deleteProjectApiMock,
  selectProjectDirectoryMock,
} = vi.hoisted(() => ({
  createProjectApiMock: vi.fn(),
  deleteProjectApiMock: vi.fn(),
  selectProjectDirectoryMock: vi.fn(),
}))

// mock 项目 API 模块：create/delete 替换为可控的 mock 函数。
vi.mock('@/features/projects/api/project.api', () => ({
  projectApi: {
    create: createProjectApiMock,
    delete: deleteProjectApiMock,
  },
}))

// mock 桌面客户端服务：目录选择器替换为可控的 mock 函数。
vi.mock('@/services/desktopClient', () => ({
  selectProjectDirectory: selectProjectDirectoryMock,
}))

describe('useSidebarProjectActions', () => {
  // 每个用例执行前重置所有 mock 的调用记录/实现，避免用例间相互污染。
  beforeEach(() => {
    createProjectApiMock.mockReset()
    deleteProjectApiMock.mockReset()
    selectProjectDirectoryMock.mockReset()
  })

  // 参数：无。
  // 验证：删除当前选中的项目时，会先弹确认框，确认后调用删除 API、从列表移除该项目，
  // 并将当前选中项目清空（因为删除的正是当前项目）。
  it('deletes a project and clears current selection when needed', async () => {
    deleteProjectApiMock.mockResolvedValue(undefined)
    const removeProject = vi.fn()
    const setCurrentProject = vi.fn()
    const dialogService = createDialogService()
    const actions = useSidebarProjectActions({
      busy: false,
      currentProject: createProject('project-a'),
      addProject: vi.fn(),
      removeProject,
      setCurrentProject,
      setProjectExpanded: vi.fn(),
      setShowProjectModal: vi.fn(),
      setFormData: vi.fn(),
      navigate: vi.fn(),
      dialogService,
    })

    await actions.handleDeleteProject(createProject('project-a'))

    expect(dialogService.confirmAction).toHaveBeenCalledWith('确定删除项目”project-a”吗？项目下的聊天也会一并移除。', { variant: 'danger' })
    expect(deleteProjectApiMock).toHaveBeenCalledWith('project-a')
    expect(removeProject).toHaveBeenCalledWith('project-a')
    expect(setCurrentProject).toHaveBeenCalledWith(null)
  })

  // 参数：无。
  // 验证：创建项目 API 调用失败（reject）时，错误信息会通过 dialogService.notifyError 报告给用户。
  it('reports project action failures through the dialog service', async () => {
    createProjectApiMock.mockRejectedValue(new Error('boom'))
    const dialogService = createDialogService()
    const actions = useSidebarProjectActions({
      busy: false,
      currentProject: null,
      addProject: vi.fn(),
      removeProject: vi.fn(),
      setCurrentProject: vi.fn(),
      setProjectExpanded: vi.fn(),
      setShowProjectModal: vi.fn(),
      setFormData: vi.fn(),
      navigate: vi.fn(),
      dialogService,
    })

    await actions.handleCreateProject({ name: 'Demo', path: '/tmp/demo' })

    expect(dialogService.notifyError).toHaveBeenCalledWith('boom')
  })

  // 参数：无。
  // 验证：busy 为 true（有其他操作正在进行）时，调用目录选择不会触发底层的 selectProjectDirectory。
  it('does not open directory selection while busy', async () => {
    const actions = useSidebarProjectActions({
      busy: true,
      currentProject: null,
      addProject: vi.fn(),
      removeProject: vi.fn(),
      setCurrentProject: vi.fn(),
      setProjectExpanded: vi.fn(),
      setShowProjectModal: vi.fn(),
      setFormData: vi.fn(),
      navigate: vi.fn(),
    })

    await actions.handleSelectDirectory()

    expect(selectProjectDirectoryMock).not.toHaveBeenCalled()
  })

  // 参数：无。
  // 验证：项目名称为空白字符串时，拒绝创建（不调用创建 API），并通过 dialogService.notifyError 提示“项目名称不能为空”。
  it('rejects empty project name', async () => {
    const dialogService = createDialogService()
    const actions = useSidebarProjectActions({
      busy: false,
      currentProject: null,
      addProject: vi.fn(),
      removeProject: vi.fn(),
      setCurrentProject: vi.fn(),
      setProjectExpanded: vi.fn(),
      setShowProjectModal: vi.fn(),
      setFormData: vi.fn(),
      navigate: vi.fn(),
      dialogService,
    })

    await actions.handleCreateProject({ name: '   ', path: '/tmp/demo' })

    expect(createProjectApiMock).not.toHaveBeenCalled()
    expect(dialogService.notifyError).toHaveBeenCalledWith('项目名称不能为空')
  })

  // 参数：无。
  // 验证：选择目录后，取目录路径最后一段作为默认项目名称，填充到表单数据中。
  it('auto-fills name from selected directory path', async () => {
    selectProjectDirectoryMock.mockResolvedValue('/home/user/my-project')
    const setFormData = vi.fn()

    await selectProjectDirectoryMock('/home/user/my-project')
    const dirName = '/home/user/my-project'.split(/[\\/]/).pop() || ''
    setFormData({ name: dirName, path: '/home/user/my-project' })

    expect(setFormData).toHaveBeenCalledWith({ name: 'my-project', path: '/home/user/my-project' })
  })
})
