import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useContextMenuStore } from '@/shared/stores/contextMenu.store'
import { useToastStore } from '@/shared/stores/toast.store'
import { useMessageContextMenu } from '../useMessageContextMenu'

function makeMouseEvent(x = 100, y = 200) {
  return {
    preventDefault: vi.fn(),
    clientX: x,
    clientY: y,
  } as unknown as React.MouseEvent
}

describe('useMessageContextMenu', () => {
  beforeEach(() => {
    useContextMenuStore.setState({ isOpen: false, x: 0, y: 0, items: [] })
    useToastStore.setState({ toasts: [] })
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
    vi.stubGlobal('window', { getSelection: vi.fn().mockReturnValue(null) })
  })

  it('prevents the native context menu and opens the store with a 复制 item', () => {
    const handler = useMessageContextMenu(() => '整条消息全文')
    const event = makeMouseEvent(10, 20)
    handler(event)

    expect(event.preventDefault).toHaveBeenCalledOnce()
    const state = useContextMenuStore.getState()
    expect(state.isOpen).toBe(true)
    expect(state.x).toBe(10)
    expect(state.y).toBe(20)
    expect(state.items).toHaveLength(1)
    expect(state.items[0].label).toBe('复制')
  })

  it('copies getFullText() result when there is no selection', async () => {
    const handler = useMessageContextMenu(() => '原始 Markdown 源码')
    handler(makeMouseEvent())

    await useContextMenuStore.getState().items[0].onClick()

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('原始 Markdown 源码')
  })

  it('copies the visible selection text instead of getFullText() when a selection exists', async () => {
    vi.stubGlobal('window', {
      getSelection: vi.fn().mockReturnValue({ isCollapsed: false, toString: () => '选中的可见文本' }),
    })
    const handler = useMessageContextMenu(() => '不应该被使用的原始 Markdown')
    handler(makeMouseEvent())

    await useContextMenuStore.getState().items[0].onClick()

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('选中的可见文本')
  })

  it('shows an info toast only after writeText resolves', async () => {
    const handler = useMessageContextMenu(() => '文本')
    handler(makeMouseEvent())

    await useContextMenuStore.getState().items[0].onClick()

    const toasts = useToastStore.getState().toasts
    expect(toasts).toHaveLength(1)
    expect(toasts[0].level).toBe('info')
    expect(toasts[0].message).toBe('已复制到剪贴板')
  })

  it('shows an error toast and does not show a success toast when writeText rejects', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } })
    const handler = useMessageContextMenu(() => '文本')
    handler(makeMouseEvent())

    await useContextMenuStore.getState().items[0].onClick()

    const toasts = useToastStore.getState().toasts
    expect(toasts).toHaveLength(1)
    expect(toasts[0].level).toBe('error')
    expect(toasts[0].message).toBe('复制失败')
  })
})
