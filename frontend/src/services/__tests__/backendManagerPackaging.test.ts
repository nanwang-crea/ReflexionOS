// backend-manager.cjs 打包相关辅助函数的单测：验证开发态与打包态下后端进程启动方案的推导，以及各平台打包产物路径的解析。
import { describe, expect, it } from 'vitest'
// @ts-expect-error CommonJS helper used by the Electron bootstrap.
import { buildBackendLaunchPlan, resolvePackagedBackendExecutable } from '../../../electron/backend-manager.cjs'

describe('backend-manager packaging helpers', () => {
  // 参数：无。
  // 验证：应用未打包（开发态）时，启动方案应使用 python3 + uvicorn 模块方式拉起后端。
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

  // 参数：无。
  // 验证：应用已打包时，启动方案应直接使用内置的后端可执行文件，不再走 Python 解释器。
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

  // 参数：无。
  // 验证：不同桌面平台（darwin/win32）下，打包产物的可执行文件名与扩展名（.exe）能被正确拼接。
  it('resolves the packaged backend executable name for each desktop platform', () => {
    expect(resolvePackagedBackendExecutable('/resources', 'darwin')).toBe(
      '/resources/backend-bin/reflexion-backend',
    )
    expect(resolvePackagedBackendExecutable('/resources', 'win32')).toBe(
      '/resources/backend-bin/reflexion-backend.exe',
    )
  })
})
