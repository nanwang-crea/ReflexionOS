import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

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
  it('renders nothing when isOpen is false', () => {
    const html = renderToStaticMarkup(
      <ContextMenu isOpen={false} x={0} y={0} items={[]} onClose={vi.fn()} />,
    )
    expect(html).toBe('')
  })

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
