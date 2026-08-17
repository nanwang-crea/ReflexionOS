// backend-runtime-requirements.cjs 的单测：验证从 requirements.txt 文本中推导出运行时需要探测的 Python 模块名列表。
import { describe, expect, it } from 'vitest'
// @ts-expect-error CommonJS helper used by the Electron bootstrap.
import { probeModuleNamesFromRequirements } from '../../../electron/backend-runtime-requirements.cjs'

describe('probeModuleNamesFromRequirements', () => {
  // 参数：无。
  // 验证：能从 requirements 文本中提取“运行时依赖”分组下的包名，并跳过“测试依赖”“打包依赖”分组中的条目。
  it('derives runtime probe modules from requirements text and skips test-only entries', () => {
    const modules = probeModuleNamesFromRequirements(`
# Runtime dependencies
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic-settings==2.1.0
python-dotenv==1.0.0
openai==1.12.0
aiofiles==23.2.1
sqlalchemy==2.0.25

# Test dependencies
pytest==7.4.4
pytest-asyncio==0.23.3

# Packaging dependencies
pyinstaller==6.13.0
`)

    expect(modules).toEqual([
      'fastapi',
      'uvicorn',
      'pydantic_settings',
      'dotenv',
      'openai',
      'aiofiles',
      'sqlalchemy',
    ])
  })

  // 参数：无。
  // 验证：当发行包名（如 GitPython、PyYAML）与实际导入的模块名（git、yaml）不同时，能正确完成映射。
  it('maps distribution package names to their import module names', () => {
    const modules = probeModuleNamesFromRequirements(`
# Runtime dependencies
GitPython
PyYAML
`)

    expect(modules).toEqual([
      'git',
      'yaml',
    ])
  })
})
