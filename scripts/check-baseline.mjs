// 统一执行开发基线：校验环境、隔离后端测试数据、运行测试和构建，并保留日志及报告。
import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const scriptPath = fileURLToPath(import.meta.url)
const repoRoot = path.resolve(path.dirname(scriptPath), '..')

// 输入仓库目录和父进程环境；创建每次独立的工作目录与环境副本；返回执行上下文。
export function createRunContext(root, parentEnv = process.env) {
  const outputDir = path.join(root, '.baseline')
  fs.mkdirSync(outputDir, { recursive: true })
  const runDir = fs.mkdtempSync(path.join(outputDir, 'run-'))
  const home = path.join(runDir, 'home')
  const temp = path.join(runDir, 'tmp')
  const cwd = path.join(runDir, 'work')
  for (const directory of [home, temp, cwd]) {
    fs.mkdirSync(directory, { recursive: true })
  }
  const env = { ...parentEnv }
  for (const variable of ['PYTHONPATH', 'PYTHONHOME', 'PYTHONUSERBASE', 'PYTEST_ADDOPTS', 'PYTEST_PLUGINS']) {
    delete env[variable]
  }
  Object.assign(env, {
    HOME: home,
    USERPROFILE: home,
    TEMP: temp,
    TMP: temp,
    TMPDIR: temp,
    PYTHONUTF8: '1',
    PYTHONNOUSERSITE: '1',
    PYTHONDONTWRITEBYTECODE: '1',
    PYTEST_DISABLE_PLUGIN_AUTOLOAD: '1',
    REFLEXION_LOG_DIR: path.join(runDir, 'app-logs'),
    // 浏览器和分词缓存先解析为绝对路径，避免 HOME 改变后丢失已准备的资源。
    PLAYWRIGHT_BROWSERS_PATH: path.resolve(root, parentEnv.PLAYWRIGHT_BROWSERS_PATH || 'backend/.cache/ms-playwright'),
    TIKTOKEN_CACHE_DIR: path.resolve(root, parentEnv.TIKTOKEN_CACHE_DIR || 'backend/.cache/tiktoken'),
  })
  return { runDir, cwd, env, results: [] }
}

// 输入阶段名、可执行文件、参数和上下文；限时执行并保存两个输出流；返回可审计的结果。
export function runStep(name, command, args, context, timeout = 300_000) {
  console.log(`\n[${name}]`)
  const started = Date.now()
  const log = path.join(context.runDir, `${name}.log`)
  // 直接写入日志文件，让长测试可实时诊断，并在超时或进程中断时保留已经产生的输出。
  const logHandle = fs.openSync(log, 'w')
  let child
  try {
    child = spawnSync(command, args, {
      cwd: context.cwd,
      env: context.env,
      stdio: ['ignore', logHandle, logHandle],
      windowsHide: true,
      timeout,
    })
  } finally {
    fs.closeSync(logHandle)
  }
  if (child.error) fs.appendFileSync(log, '\n' + child.error.stack + '\n')
  const output = fs.readFileSync(log, 'utf8')
  const result = {
    name,
    passed: child.status === 0 && !child.error,
    exitCode: child.status,
    signal: child.signal,
    durationMs: Date.now() - started,
    log,
  }
  context.results.push(result)
  console.log(output.trim().split(/\r?\n/).slice(-18).join('\n'))
  console.log(`${result.passed ? 'PASS' : 'FAIL'}: ${name} (${result.durationMs} ms)`)
  return result
}

// 输入命令行参数；默认运行完整基线，--prepare 仅下载测试资源；返回整体退出码。
function main(args) {
  const prepare = args.length === 1 && args[0] === '--prepare'
  if (args.length && !prepare) {
    console.error('Usage: node scripts/check-baseline.mjs [--prepare]')
    return 1
  }
  const context = createRunContext(repoRoot)
  console.log(`Reports: ${context.runDir}`)
  const backendDir = path.join(repoRoot, 'backend')
  const frontendDir = path.join(repoRoot, 'frontend')
  const python = path.join(backendDir, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
  // -I 会忽略 PYTHON* 环境变量，因此通过显式参数保证 Windows 日志编码并禁止源码目录字节码写入。
  const pythonArgs = ['-I', '-B', '-X', 'utf8']
  try {
    // 版本匹配策略：只校验主版本（如 24），不锁死完整版本号。
    // 原因：GitHub Actions runner 不保证提供精确 Node patch（如 24.14.1），
    // 精确匹配会导致 CI 在 runner 升级后挂。本地可用 .node-version 锁死完整版本。
    const expectedNodeRaw = fs.readFileSync(path.join(repoRoot, '.node-version'), 'utf8').trim()
    const expectedNodeMajor = expectedNodeRaw.split('.')[0]
    const actualNodeMajor = String(process.versions.node).split('.')[0]
    if (actualNodeMajor !== expectedNodeMajor) {
      throw new Error(`Node ${expectedNodeMajor}.x required; found ${process.versions.node}`)
    }
    console.log(`Node ${process.versions.node}; ${process.platform}/${process.arch}`)
    const pythonReady = runStep('python-environment', python, [
      ...pythonArgs, path.join(repoRoot, 'scripts/check-python-env.py'),
    ], context).passed
    const dependenciesReady = pythonReady && runStep('python-dependencies', python, [
      ...pythonArgs, '-m', 'pip', 'check',
    ], context).passed

    if (dependenciesReady) {
      // 保留实际安装快照，方便与锁文件及其他平台的检查结果对照。
      runStep('python-packages', python, [...pythonArgs, '-m', 'pip', 'freeze', '--all'], context)
      if (prepare) {
        runStep('install-chromium', python, [...pythonArgs, '-m', 'playwright', 'install', 'chromium'], context, 600_000)
        runStep('prepare-tokenizers', python, [
          ...pythonArgs, '-c', 'import tiktoken; tiktoken.get_encoding("cl100k_base"); tiktoken.get_encoding("o200k_base"); print("Tokenizers ready")',
        ], context)
      } else {
        runStep('python-environment-tests', python, [
          ...pythonArgs, '-m', 'unittest', 'discover',
          '-s', path.join(repoRoot, 'scripts'), '-p', 'test_check_python_env.py',
        ], context)
        runStep('backend-tests', python, [
          ...pythonArgs, '-m', 'pytest', path.join(backendDir, 'tests'),
          '-c', path.join(backendDir, 'pyproject.toml'),
          '-p', 'pytest_asyncio.plugin', '-q', '-ra',
          '--basetemp', path.join(context.runDir, 'pytest-tmp'),
          '-o', `cache_dir=${path.join(context.runDir, 'pytest-cache')}`,
          `--junitxml=${path.join(context.runDir, 'backend-junit.xml')}`,
        ], context, 900_000)
      }
    } else {
      console.error('Backend checks stopped: recreate backend/.venv and install backend/requirements.lock.')
    }

    if (!prepare) {
      runStep('baseline-runner-tests', process.execPath, [
        '--test', path.join(repoRoot, 'scripts/check-baseline.test.mjs'),
      ], context)
      // 对照 pnpm 安装时保存的锁文件，发现过期 node_modules 时要求先冻结安装。
      const expectedLock = fs.readFileSync(path.join(frontendDir, 'pnpm-lock.yaml'), 'utf8').replaceAll('\r\n', '\n').trim()
      const installedLock = fs.readFileSync(path.join(frontendDir, 'node_modules/.pnpm/lock.yaml'), 'utf8').replaceAll('\r\n', '\n').trim()
      if (expectedLock !== installedLock) {
        throw new Error('Frontend install is stale; run pnpm install --frozen-lockfile in frontend/')
      }
      const frontendContext = { ...context, cwd: frontendDir }
      // 直接调用已冻结安装的 Node 入口，避免 Windows .cmd 与 shell 引号规则差异。
      runStep('frontend-tests', process.execPath, [
        path.join(frontendDir, 'node_modules/vitest/vitest.mjs'), 'run',
        '--reporter=default', '--reporter=junit',
        `--outputFile.junit=${path.join(context.runDir, 'frontend-junit.xml')}`,
      ], frontendContext)
      if (runStep('frontend-types', process.execPath, [
        path.join(frontendDir, 'node_modules/typescript/bin/tsc'),
      ], frontendContext).passed) {
        runStep('frontend-build', process.execPath, [
          path.join(frontendDir, 'node_modules/vite/bin/vite.js'), 'build',
        ], frontendContext)
      }
    }
  } catch (error) {
    console.error(error.message)
    context.results.push({ name: 'baseline-setup', passed: false, error: error.message })
  }
  const passed = context.results.length > 0 && context.results.every(result => result.passed)
  fs.writeFileSync(path.join(context.runDir, 'summary.json'), JSON.stringify({
    mode: prepare ? 'prepare' : 'check',
    passed,
    timestamp: new Date().toISOString(),
    node: process.versions.node,
    platform: process.platform,
    results: context.results,
  }, null, 2) + '\n')
  console.log(`\n${prepare ? 'Preparation' : 'Baseline'} ${passed ? 'PASSED' : 'FAILED'}. Reports: ${context.runDir}`)
  return passed ? 0 : 1
}

if (process.argv[1] && path.resolve(process.argv[1]) === scriptPath) {
  process.exitCode = main(process.argv.slice(2))
}
