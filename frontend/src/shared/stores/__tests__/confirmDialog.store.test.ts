import { afterEach, describe, expect, it } from 'vitest'
import { useConfirmDialogStore } from '../confirmDialog.store'

describe('confirmDialog.store', () => {
  afterEach(() => {
    // 每个用例后复位为初始关闭态，避免相互影响
    useConfirmDialogStore.setState({ open: false, title: undefined, message: '', variant: 'default', resolve: null })
  })

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

  it('resolveConfirm(true) 兑现 Promise 为 true 并关闭弹框', async () => {
    const promise = useConfirmDialogStore.getState().requestConfirm('确定?')
    useConfirmDialogStore.getState().resolveConfirm(true)
    await expect(promise).resolves.toBe(true)
    expect(useConfirmDialogStore.getState().open).toBe(false)
    expect(useConfirmDialogStore.getState().resolve).toBeNull()
  })

  it('resolveConfirm(false) 兑现 Promise 为 false 并关闭弹框', async () => {
    const promise = useConfirmDialogStore.getState().requestConfirm('确定?')
    useConfirmDialogStore.getState().resolveConfirm(false)
    await expect(promise).resolves.toBe(false)
    expect(useConfirmDialogStore.getState().open).toBe(false)
  })

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

  it('resolveConfirm 只兑现一次:重复调用不抛错且无副作用', async () => {
    const promise = useConfirmDialogStore.getState().requestConfirm('确定?')
    useConfirmDialogStore.getState().resolveConfirm(true)
    // 第二次调用时 resolve 已置空,应安全 no-op
    expect(() => useConfirmDialogStore.getState().resolveConfirm(false)).not.toThrow()
    await expect(promise).resolves.toBe(true)
  })
})
