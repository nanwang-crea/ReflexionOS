const fs = require('fs')

const IMPORT_NAME_OVERRIDES = {
  'pydantic-settings': 'pydantic_settings',
  'python-dotenv': 'dotenv',
}

const TEST_SECTION_HEADER = /^#\s*(test|tests|development|dev)(?:\s+dependencies)?\s*$/i
const RUNTIME_SECTION_HEADER = /^#\s*runtime(?:\s+dependencies)?\s*$/i
const DEFAULT_IGNORED_PACKAGES = new Set(['pytest', 'pytest-asyncio'])

function toRequirementName(line) {
  const normalizedLine = line.split('#', 1)[0].trim()
  if (!normalizedLine || normalizedLine.startsWith('-')) {
    return null
  }

  const match = normalizedLine.match(/^([A-Za-z0-9_.-]+)/)
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

    if (TEST_SECTION_HEADER.test(line)) {
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
