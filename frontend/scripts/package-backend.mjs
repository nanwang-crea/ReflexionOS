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

// 使用 backend/.venv 中的 pyinstaller（而非全局 Python 环境），避免全局环境里
// 其他项目安装的无关重型依赖（torch/nltk/transformers 等）被误打包进后端 exe
const venvPyinstaller = process.platform === 'win32'
  ? path.join(backendDir, '.venv', 'Scripts', 'pyinstaller.exe')
  : path.join(backendDir, '.venv', 'bin', 'pyinstaller')
const pyinstallerCommand = fs.existsSync(venvPyinstaller)
  ? venvPyinstaller
  : (process.platform === 'win32' ? 'pyinstaller.exe' : 'pyinstaller')
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
