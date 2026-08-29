// ContextMenu 组件的渲染测试：mock framer-motion 为普通 div/透传，避免动画库副作用，
// 用 renderToStaticMarkup 断言关闭态不渲染、打开态按坐标定位并渲染菜单项。
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

// mock framer-motion：AnimatePresence 直接渲染 children，motion.div 退化为普通 div，
// 使静态渲染测试不依赖动画实现细节。
vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement> & { children?: React.ReactNode }) => (
      <div {...props}>{children}</div>
    ),
  },
}))

import { ContextMenu } from '../ContextMenu'

describe('ContextMenu', () => {
  // 参数：无。
  // 验证：isOpen 为 false 时组件不渲染任何 DOM（渲染结果为空字符串）。
  it('renders nothing when isOpen is false', () => {
    const html = renderToStaticMarkup(
      <ContextMenu isOpen={false} x={0} y={0} items={[]} onClose={vi.fn()} />,
    )
    expect(html).toBe('')
  })

  // 参数：无。
  // 验证：isOpen 为 true 时按传入的 x/y 坐标定位菜单（style 中包含 left/top），
  // 并渲染出 items 中的菜单项文案。
  it('renders the menu items at the given coordinates when open', () => {
    const html = renderToStaticMarkup(
      <ContextMenu
        isOpen={true}
        x={120}
        y={240}
        items={[{ label: '复制', onClick: vi.fn() }]}
        onClose={vi.fn()}
      />,
    )
    expect(html).toContain('复制')
    expect(html).toContain('left:120px')
    expect(html).toContain('top:240px')
  })
})
