// 验证基线入口的数据隔离、失败退出和日志保留，防止环境故障被报告为通过。
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { createRunContext, runStep } from './check-baseline.mjs'

// 输入测试上下文；创建独立目录并注册清理；返回临时仓库根目录。
function temporaryRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'reflexion-baseline-'))
  t.after(() => fs.rmSync(root, { recursive: true, force: true }))
  return root
}

test('each run isolates application data and removes inherited Python test options', (t) => {
  const root = temporaryRoot(t)
  const inherited = {
    ...process.env,
    HOME: path.join(root, 'real-home'),
    USERPROFILE: path.join(root, 'real-home'),
    PYTHONPATH: 'unrelated-packages',
    PYTHONHOME: 'unrelated-python',
    PYTEST_ADDOPTS: '-k no_tests',
    PYTEST_PLUGINS: 'unrelated_plugin',
    PLAYWRIGHT_BROWSERS_PATH: path.join(root, 'browsers'),
  }
  const first = createRunContext(root, inherited)
  const second = createRunContext(root, inherited)

  assert.notEqual(first.runDir, second.runDir)
  assert.equal(first.env.HOME, first.env.USERPROFILE)
  assert.notEqual(first.env.HOME, inherited.HOME)
  for (const directory of [first.cwd, first.env.HOME, first.env.TEMP, first.env.TMP]) {
    assert.ok(fs.statSync(directory).isDirectory())
    assert.ok(directory.startsWith(first.runDir + path.sep))
  }
  for (const variable of ['PYTHONPATH', 'PYTHONHOME', 'PYTEST_ADDOPTS', 'PYTEST_PLUGINS']) {
    assert.equal(first.env[variable], undefined)
  }
  assert.equal(first.env.PLAYWRIGHT_BROWSERS_PATH, inherited.PLAYWRIGHT_BROWSERS_PATH)
  assert.equal(inherited.PYTEST_ADDOPTS, '-k no_tests')
})

test('a failing command retains both output streams and its exit code', (t) => {
  const context = createRunContext(temporaryRoot(t))
  const result = runStep('intentional-failure', process.execPath, [
    '-e', 'console.log("stdout evidence 中文"); console.error("stderr evidence"); process.exit(7)',
  ], context)

  assert.equal(result.passed, false)
  assert.equal(result.exitCode, 7)
  const log = fs.readFileSync(result.log, 'utf8')
  assert.match(log, /stdout evidence 中文/)
  assert.match(log, /stderr evidence/)
})

test('a missing executable is a failed step with an actionable log', (t) => {
  const context = createRunContext(temporaryRoot(t))
  const result = runStep('missing-tool', path.join(context.runDir, 'missing-python'), [], context)

  assert.equal(result.passed, false)
  assert.match(fs.readFileSync(result.log, 'utf8'), /ENOENT/)
})
