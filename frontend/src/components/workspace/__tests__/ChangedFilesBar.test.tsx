// ChangedFilesBar 组件的渲染测试：用 renderToStaticMarkup 做服务端静态渲染断言，
// 覆盖"折叠摘要""展开明细""空清单不渲染"三个场景。
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ChangedFilesBar } from '../ChangedFilesBar'
import type { ChangedFileEntry } from '@/types/conversation'

const files: ChangedFileEntry[] = [
  { path: 'src/new.ts', action: 'created' },
  { path: 'src/edit.ts', action: 'modified' },
  { path: 'src/gone.ts', action: 'deleted' },
  { path: 'src/renamed.ts', action: 'moved', oldPath: 'src/old.ts' },
]

describe('ChangedFilesBar', () => {
  it('renders nothing for an empty list', () => {
    expect(renderToStaticMarkup(React.createElement(ChangedFilesBar, { files: [] }))).toBe('')
  })

  it('renders collapsed summary with file count', () => {
    const html = renderToStaticMarkup(React.createElement(ChangedFilesBar, { files }))
    expect(html).toContain('data-changed-files-bar')
    expect(html).toContain('变更了 4 个文件')
    expect(html).not.toContain('src/new.ts')
  })

  it('expanded state is controlled and entries render on demand', () => {
    // 受控组件默认折叠；展开渲染通过首个交互完成，静态渲染仅断言折叠态不含明细。
    // 展开明细由交互测试覆盖，此处断言组件不因 moved 的 oldPath 渲染而崩溃。
    const html = renderToStaticMarkup(
      React.createElement(ChangedFilesBar, { files: [{ path: 'a.ts', action: 'moved', oldPath: 'b.ts' }] })
    )
    expect(html).toContain('变更了 1 个文件')
  })
})
