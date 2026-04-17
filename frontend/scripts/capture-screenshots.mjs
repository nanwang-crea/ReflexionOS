import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(__dirname, '..')
const repoRoot = path.resolve(frontendDir, '..')
const electronBinary = path.join(
  frontendDir,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'electron.cmd' : 'electron',
)
const outputDir = path.join(repoRoot, '.github', 'assets')

const child = spawn(electronBinary, ['./electron/main.cjs'], {
  cwd: frontendDir,
  env: {
    ...process.env,
    REFLEXION_CAPTURE_DIR: outputDir,
    REFLEXION_CAPTURE_SCENES: 'agent,projects',
  },
  stdio: 'inherit',
})

child.on('exit', (code) => {
  process.exit(code ?? 0)
})
