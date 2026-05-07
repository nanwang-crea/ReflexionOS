import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '../..')
const backendDir = path.join(repoRoot, 'backend')
const cacheDir = path.join(backendDir, 'build', 'pyinstaller-cache')
const specPath = path.join(repoRoot, 'packaging', 'pyinstaller', 'reflexion-backend.spec')

fs.mkdirSync(cacheDir, { recursive: true })

const pyinstallerCommand = process.platform === 'win32' ? 'pyinstaller.exe' : 'pyinstaller'
const result = spawnSync(
  pyinstallerCommand,
  ['--clean', '--noconfirm', '--workpath', 'build', '--distpath', 'dist', specPath],
  {
    cwd: backendDir,
    env: {
      ...process.env,
      PYINSTALLER_CONFIG_DIR: cacheDir,
    },
    stdio: 'inherit',
  },
)

if (result.error) {
  throw result.error
}

process.exit(result.status ?? 1)
