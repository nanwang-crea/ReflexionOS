// 文件功能：confirmDialog.store 的单元测试
// 文件描述：验证应用内确认弹框 store 的核心行为：发起确认请求、用户确认/取消后的
//           Promise 兑现、以及“同一时刻只允许一个弹框”的单例约束
// 核心逻辑：每个用例结束后复位 store 到初始关闭态，避免用例间状态相互污染
import { afterEach, describe, expect, it } from 'vitest'
import { useConfirmDialogStore } from '../confirmDialog.store'

describe('confirmDialog.store', () => {
  afterEach(() => {
    // 每个用例后复位为初始关闭态，避免相互影响
    useConfirmDialogStore.setState({ open: false, title: undefined, message: '', variant: 'default', resolve: null })
  })

  /**
   * 用例：requestConfirm 打开弹框并写入请求,返回未兑现的 Promise
   * 验证点：调用 requestConfirm 后，store 状态应立即变为打开，
   *         并写入传入的 message/variant/title，且 resolve 引用已就位（尚未兑现）
   */
  it('requestConfirm 打开弹框并写入请求,返回未兑现的 Promise', () => {
    const promise = useConfirmDialogStore.getState().requestConfirm('确定删除吗?', { variant: 'danger', title: '危险操作' })
    const state = useConfirmDialogStore.getState()
    expect(state.open).toBe(true)
    expect(state.message).toBe('确定删除吗?')
    expect(state.variant).toBe('danger')
    expect(state.title).toBe('危险操作')
    expect(typeof state.resolve).toBe('function')
    // promise 仍挂起;后续由 resolveConfirm 兑现
    void promise
  })

  /**
   * 用例：resolveConfirm(true) 兑现 Promise 为 true 并关闭弹框
   * 验证点：调用 resolveConfirm(true) 后，之前 requestConfirm 返回的 Promise 应
   *         resolve 为 true，且弹框状态恢复为关闭、resolve 引用被清空
   */
  it('resolveConfirm(true) 兑现 Promise 为 true 并关闭弹框', async () => {
    const promise = useConfirmDialogStore.getState().requestConfirm('确定?')
    useConfirmDialogStore.getState().resolveConfirm(true)
    await expect(promise).resolves.toBe(true)
    expect(useConfirmDialogStore.getState().open).toBe(false)
    expect(useConfirmDialogStore.getState().resolve).toBeNull()
  })

  /**
   * 用例：resolveConfirm(false) 兑现 Promise 为 false 并关闭弹框
   * 验证点：用户取消场景下，Promise 应 resolve 为 false，弹框同样关闭
   */
  it('resolveConfirm(false) 兑现 Promise 为 false 并关闭弹框', async () => {
    const promise = useConfirmDialogStore.getState().requestConfirm('确定?')
    useConfirmDialogStore.getState().resolveConfirm(false)
    await expect(promise).resolves.toBe(false)
    expect(useConfirmDialogStore.getState().open).toBe(false)
  })

  /**
   * 用例：已有弹框打开时再次 requestConfirm,直接 resolve 新请求为 false(拒绝堆叠)
   * 验证点：第二次请求应立即被拒绝为 false，且不影响第一个请求的状态（message 未被覆盖）；
   *         最终收尾兑现第一个请求，确认其 Promise 仍能正常 resolve
   */
  it('已有弹框打开时再次 requestConfirm,直接 resolve 新请求为 false(拒绝堆叠)', async () => {
    const first = useConfirmDialogStore.getState().requestConfirm('第一个')
    const second = useConfirmDialogStore.getState().requestConfirm('第二个')
    // 新请求被直接拒绝
    await expect(second).resolves.toBe(false)
    // 第一个弹框仍在,message 未被覆盖
    expect(useConfirmDialogStore.getState().message).toBe('第一个')
    // 收尾:兑现第一个
    useConfirmDialogStore.getState().resolveConfirm(true)
    await expect(first).resolves.toBe(true)
  })

  /**
   * 用例：resolveConfirm 只兑现一次:重复调用不抛错且无副作用
   * 验证点：resolve 引用被清空后再次调用 resolveConfirm 应安全 no-op（不抛错），
   *         且不影响第一次兑现的结果
   */
  it('resolveConfirm 只兑现一次:重复调用不抛错且无副作用', async () => {
    const promise = useConfirmDialogStore.getState().requestConfirm('确定?')
    useConfirmDialogStore.getState().resolveConfirm(true)
    // 第二次调用时 resolve 已置空,应安全 no-op
    expect(() => useConfirmDialogStore.getState().resolveConfirm(false)).not.toThrow()
    await expect(promise).resolves.toBe(true)
  })
})
