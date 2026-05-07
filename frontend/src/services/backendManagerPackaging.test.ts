import { describe, expect, it } from 'vitest'
// @ts-expect-error CommonJS helper used by the Electron bootstrap.
import { buildBackendLaunchPlan, resolvePackagedBackendExecutable } from '../../electron/backend-manager.cjs'

describe('backend-manager packaging helpers', () => {
  it('keeps the Python uvicorn launch path for development', () => {
    const plan = buildBackendLaunchPlan({
      appIsPackaged: false,
      backendDir: '/repo/backend',
      backendExecutablePath: null,
      pythonCommand: 'python3',
      platform: 'darwin',
    })

    expect(plan).toEqual({
      command: 'python3',
      args: ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'],
      cwd: '/repo/backend',
      mode: 'python',
    })
  })

  it('uses the bundled backend executable when the app is packaged', () => {
    const plan = buildBackendLaunchPlan({
      appIsPackaged: true,
      backendDir: '/repo/backend',
      backendExecutablePath: '/app/Contents/Resources/backend-bin/reflexion-backend',
      pythonCommand: 'python3',
      platform: 'darwin',
    })

    expect(plan).toEqual({
      command: '/app/Contents/Resources/backend-bin/reflexion-backend',
      args: [],
      cwd: '/app/Contents/Resources/backend-bin',
      mode: 'packaged',
    })
  })

  it('resolves the packaged backend executable name for each desktop platform', () => {
    expect(resolvePackagedBackendExecutable('/resources', 'darwin')).toBe(
      '/resources/backend-bin/reflexion-backend',
    )
    expect(resolvePackagedBackendExecutable('/resources', 'win32')).toBe(
      '/resources/backend-bin/reflexion-backend.exe',
    )
  })
})
