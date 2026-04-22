import { describe, expect, it } from 'vitest'
// @ts-expect-error CommonJS helper used by the Electron bootstrap.
import { probeModuleNamesFromRequirements } from '../../electron/backend-runtime-requirements.cjs'

describe('probeModuleNamesFromRequirements', () => {
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
})
