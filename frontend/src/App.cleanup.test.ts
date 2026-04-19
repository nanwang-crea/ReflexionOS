import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

describe('App cleanup', () => {
  it('does not keep the legacy /projects route once sidebar project management is the primary path', () => {
    const appSource = readFileSync(
      path.resolve(__dirname, 'App.tsx'),
      'utf8'
    )

    expect(appSource.includes("path=\"/projects\"")).toBe(false)
  })
})
