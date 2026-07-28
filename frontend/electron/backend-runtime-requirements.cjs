const fs = require('fs')

const IMPORT_NAME_OVERRIDES = {
  gitpython: 'git',
  'pydantic-settings': 'pydantic_settings',
  pyyaml: 'yaml',
  'python-dotenv': 'dotenv',
}

const NON_RUNTIME_SECTION_HEADER = /^#\s*(test|tests|development|dev|packaging)(?:\s+dependencies)?\s*$/i
const RUNTIME_SECTION_HEADER = /^#\s*runtime(?:\s+dependencies)?\s*$/i
const DEFAULT_IGNORED_PACKAGES = new Set(['pytest', 'pytest-asyncio'])

/**
 * Evaluate a pip environment marker (the part after `;` in a requirement line).
 * Returns true when the marker is satisfied on the current platform.
 *
 * Supports the most common markers used in requirements.txt:
 *   sys_platform == "win32"
 *   sys_platform != "darwin"
 *   platform_system == "Windows"
 *
 * If a marker can't be parsed, it is treated as satisfied (safe default).
 */
function markerMatchesCurrentPlatform(marker) {
  if (!marker) {
    return true
  }

  const sysPlatform = process.platform // 'win32' | 'darwin' | 'linux'
  const platformSystem =
    sysPlatform === 'win32' ? 'Windows' :
    sysPlatform === 'darwin' ? 'Darwin' :
    'Linux'

  // sys_platform == "win32"
  let m = marker.match(/sys_platform\s*(==|!=)\s*["']([\w]+)["']/)
  if (m) {
    const op = m[1]
    const value = m[2]
    const result = sysPlatform === value
    return op === '==' ? result : !result
  }

  // platform_system == "Windows"
  m = marker.match(/platform_system\s*(==|!=)\s*["']([\w]+)["']/)
  if (m) {
    const op = m[1]
    const value = m[2]
    const result = platformSystem === value
    return op === '==' ? result : !result
  }

  // Unknown marker — assume it matches to avoid false negatives
  return true
}

function toRequirementName(line) {
  const normalizedLine = line.split('#', 1)[0].trim()
  if (!normalizedLine || normalizedLine.startsWith('-')) {
    return null
  }

  // Split on `;` to separate the package spec from the environment marker
  const [packagePart, ...markerParts] = normalizedLine.split(';')
  const marker = markerParts.join(';').trim()

  // Skip the package if its marker doesn't match the current platform
  if (!markerMatchesCurrentPlatform(marker)) {
    return null
  }

  const match = packagePart.match(/^([A-Za-z0-9_.-]+)/)
  return match ? match[1].toLowerCase() : null
}

function toImportName(requirementName) {
  if (!requirementName) {
    return null
  }

  return IMPORT_NAME_OVERRIDES[requirementName] || requirementName.replace(/-/g, '_')
}

function probeModuleNamesFromRequirements(text) {
  const modules = []
  const seen = new Set()
  let inRuntimeSection = true

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim()

    if (!line) {
      continue
    }

    if (RUNTIME_SECTION_HEADER.test(line)) {
      inRuntimeSection = true
      continue
    }

    if (NON_RUNTIME_SECTION_HEADER.test(line)) {
      inRuntimeSection = false
      continue
    }

    if (!inRuntimeSection) {
      continue
    }

    const requirementName = toRequirementName(line)
    if (!requirementName || DEFAULT_IGNORED_PACKAGES.has(requirementName)) {
      continue
    }

    const moduleName = toImportName(requirementName)
    if (moduleName && !seen.has(moduleName)) {
      seen.add(moduleName)
      modules.push(moduleName)
    }
  }

  return modules
}

function readProbeModuleNames(requirementsPath) {
  return probeModuleNamesFromRequirements(fs.readFileSync(requirementsPath, 'utf8'))
}

function buildImportProbeCode(moduleNames) {
  if (!moduleNames.length) {
    return 'print("ok")'
  }

  return `import ${moduleNames.join(', ')}`
}

module.exports = {
  buildImportProbeCode,
  probeModuleNamesFromRequirements,
  readProbeModuleNames,
}
