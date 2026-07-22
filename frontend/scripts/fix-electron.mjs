/**
 * fix-electron.mjs
 *
 * On macOS 15+ (especially 26.x), Gatekeeper may silently remove the unsigned
 * Electron.app bundle from node_modules after it is downloaded by Electron's
 * postinstall script. This leaves behind only metadata files (LICENSE, version)
 * while the actual binary disappears, causing `spawn ... ENOENT` errors when
 * `pnpm dev` tries to launch Electron.
 *
 * This script:
 *   1. Detects whether the Electron binary is missing
 *   2. Re-runs Electron's install.js to re-download it
 *   3. Strips com.apple.provenance / quarantine attributes
 *   4. Ad-hoc signs the Electron.app so macOS stops removing it
 *
 * Usage:
 *   node ./scripts/fix-electron.mjs          # check + fix if needed
 *   node ./scripts/fix-electron.mjs --force  # always re-download + sign
 *
 * It is called automatically:
 *   - after `pnpm install` (via the postinstall hook in package.json)
 *   - before launching Electron in dev-electron.mjs
 */

import fs from 'node:fs'
import path from 'node:path'
import { execSync, spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(__dirname, '..')
const force = process.argv.includes('--force')

// ── Path helpers ──────────────────────────────────────

/** Resolve the electron package directory inside the pnpm store. */
function resolveElectronPkgDir() {
  // node_modules/electron is a symlink to .pnpm/electron@x.y.z/node_modules/electron
  const linkPath = path.join(frontendDir, 'node_modules', 'electron')
  const resolved = fs.realpathSync(linkPath)
  return resolved
}

/** Return the platform-specific binary path inside dist/. */
function getBinaryPath() {
  switch (process.platform) {
    case 'darwin':
      return 'Electron.app/Contents/MacOS/Electron'
    case 'win32':
      return 'electron.exe'
    case 'linux':
      return 'electron'
    default:
      return 'electron'
  }
}

// ── Core logic ─────────────────────────────────────────

/** Returns true if the Electron binary exists at the expected path. */
function isBinaryPresent(electronDir, binaryRelPath) {
  const binaryPath = path.join(electronDir, 'dist', binaryRelPath)
  return fs.existsSync(binaryPath)
}

/** Remove path.txt so Electron's isInstalled() returns false and forces re-download. */
function resetInstallState(electronDir) {
  const pathTxt = path.join(electronDir, 'path.txt')
  if (fs.existsSync(pathTxt)) {
    fs.rmSync(pathTxt, { force: true })
  }
}

/** Run Electron's install.js to download the binary. */
function downloadBinary(electronDir) {
  const installScript = path.join(electronDir, 'install.js')
  if (!fs.existsSync(installScript)) {
    console.warn('[fix-electron] install.js not found, skipping download')
    return
  }

  console.log('[fix-electron] Downloading Electron binary…')
  const result = spawnSync('node', [installScript], {
    cwd: electronDir,
    stdio: 'inherit',
    env: {
      ...process.env,
      // Ensure the download is not skipped
      ELECTRON_SKIP_BINARY_DOWNLOAD: '',
    },
  })

  if (result.status !== 0) {
    throw new Error(`Electron install.js exited with code ${result.status}`)
  }
}

/** Strip macOS extended attributes (com.apple.provenance, com.apple.quarantine, etc.). */
function stripXattr(distDir) {
  if (process.platform !== 'darwin') {
    return
  }

  try {
    execSync(`xattr -cr "${distDir}"`, { stdio: 'ignore' })
    console.log('[fix-electron] Stripped macOS extended attributes')
  } catch {
    // xattr might not be available, non-fatal
  }
}

/** Ad-hoc sign the Electron.app so Gatekeeper won't remove it. */
function adHocSign(electronDir, binaryRelPath) {
  if (process.platform !== 'darwin') {
    return
  }

  // The .app bundle is the first path segment of binaryRelPath
  const appBundleName = binaryRelPath.split('/')[0] // "Electron.app"
  const appBundlePath = path.join(electronDir, 'dist', appBundleName)

  if (!fs.existsSync(appBundlePath)) {
    return
  }

  try {
    execSync(`codesign --force --deep --sign - "${appBundlePath}"`, {
      stdio: 'ignore',
    })
    console.log('[fix-electron] Ad-hoc signed Electron.app')
  } catch {
    console.warn('[fix-electron] codesign failed (is Xcode Command Line Tools installed?)')
  }
}

// ── Main ───────────────────────────────────────────────

function main() {
  const electronDir = resolveElectronPkgDir()
  const binaryRelPath = getBinaryPath()
  const distDir = path.join(electronDir, 'dist')

  const present = isBinaryPresent(electronDir, binaryRelPath)

  if (present && !force) {
    // Binary exists, but on macOS we still want to ensure signing is intact
    if (process.platform === 'darwin') {
      const appBundleName = binaryRelPath.split('/')[0]
      const appBundlePath = path.join(distDir, appBundleName)
      try {
        execSync(`codesign --verify "${appBundlePath}"`, { stdio: 'ignore' })
      } catch {
        console.log('[fix-electron] Binary exists but signature is invalid — re-signing…')
        stripXattr(distDir)
        adHocSign(electronDir, binaryRelPath)
      }
    }
    return
  }

  console.log('[fix-electron] Electron binary is missing, repairing…')

  // 1. Reset install state so install.js will re-download
  resetInstallState(electronDir)

  // 2. Re-download
  downloadBinary(electronDir)

  // 3. Verify
  if (!isBinaryPresent(electronDir, binaryRelPath)) {
    throw new Error('Electron binary still missing after re-download')
  }

  // 4. Strip macOS security attributes
  stripXattr(distDir)

  // 5. Ad-hoc sign
  adHocSign(electronDir, binaryRelPath)

  console.log('[fix-electron] Electron binary repaired successfully.')
}

main()
