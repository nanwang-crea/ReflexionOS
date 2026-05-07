import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '../..')
const frontendDir = path.join(repoRoot, 'frontend')
const pyinstallerDistDir = path.join(repoRoot, 'backend', 'dist', 'reflexion-backend')
const backendBinDir = path.join(frontendDir, 'build-resources', 'backend-bin')

if (!fs.existsSync(pyinstallerDistDir)) {
  throw new Error(
    `Missing PyInstaller output at ${pyinstallerDistDir}. Run pnpm package:backend first.`,
  )
}

fs.rmSync(backendBinDir, { recursive: true, force: true })
fs.mkdirSync(backendBinDir, { recursive: true })
fs.cpSync(pyinstallerDistDir, backendBinDir, { recursive: true })
