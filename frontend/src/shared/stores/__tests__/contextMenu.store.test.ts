// 文件功能：contextMenu.store 的单元测试
// 文件描述：验证应用内自绘右键菜单 store 的核心行为：打开菜单写入坐标与菜单项、
//           单例覆盖（重复打开时以新状态覆盖旧状态）、关闭菜单清空状态
// 核心逻辑：每个用例前重置 store 到初始关闭态，避免用例间状态相互污染
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useContextMenuStore } from '../contextMenu.store'

describe('contextMenuStore', () => {
  beforeEach(() => {
    useContextMenuStore.setState({ isOpen: false, x: 0, y: 0, items: [] })
  })

  /**
   * 用例：open sets isOpen, coordinates, and items
   * 验证点：调用 open 后，isOpen 应为 true，坐标与菜单项应与传入参数一致
   */
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

  /**
   * 用例：open overwrites a previously open menu (single instance)
   * 验证点：在菜单已打开的情况下再次调用 open，应以新坐标和新菜单项完全覆盖旧状态
   *         （验证单例约束——不会出现多个菜单叠加的情况）
   */
  it('open overwrites a previously open menu (single instance)', () => {
    useContextMenuStore.getState().open(10, 10, [{ label: 'A', onClick: vi.fn() }])
    useContextMenuStore.getState().open(50, 60, [{ label: 'B', onClick: vi.fn() }])

    const state = useContextMenuStore.getState()
    expect(state.x).toBe(50)
    expect(state.y).toBe(60)
    expect(state.items[0].label).toBe('B')
  })

  /**
   * 用例：close resets isOpen and clears items
   * 验证点：调用 close 后，isOpen 应变为 false，且菜单项列表被清空
   */
  it('close resets isOpen and clears items', () => {
    useContextMenuStore.getState().open(10, 10, [{ label: 'A', onClick: vi.fn() }])
    useContextMenuStore.getState().close()

    const state = useContextMenuStore.getState()
    expect(state.isOpen).toBe(false)
    expect(state.items).toEqual([])
  })
})
