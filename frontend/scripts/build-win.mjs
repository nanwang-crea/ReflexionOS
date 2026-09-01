/**
 * build-win.mjs
 * 
 * Windows 打包脚本 —— 解决 electron-builder 在无开发者模式的 Windows 上
 * 因 macOS 符号链接(libcrypto.dylib / libssl.dylib) 导致 7za exit code 2 的问题。
 * 
 * 流程：
 *   1. pnpm build
 *   2. pnpm package:backend
 *   3. pnpm prepare:backend-bin
 *   4. electron-builder --win  （首次尝试）
 *   5. 若失败 → 自动修复 winCodeSign 缓存 → 重试
 */

import { execSync } from 'node:child_process';
import { existsSync, readdirSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';

/* ── 工具函数 ─────────────────────────────────────────── */

function run(cmd) {
  console.log(`\n▶ ${cmd}`);
  execSync(cmd, { stdio: 'inherit', cwd: process.cwd() });
}

function runTolerant(cmd) {
  console.log(`\n▶ ${cmd} (tolerant)`);
  try {
    execSync(cmd, { stdio: 'inherit', cwd: process.cwd() });
    return true;
  } catch (e) {
    // exit code 2 = symlink 警告，签名工具本身正常
    if (e.status === 2) {
      console.log('  ⚠ exit code 2 (符号链接警告，忽略)');
      return true;
    }
    console.error(`  ✗ 失败，exit code ${e.status}`);
    return false;
  }
}

/* ── 缓存修复逻辑 ────────────────────────────────────── */

function findSevenZaPath() {
  // 尝试在 node_modules 中搜索 7za.exe
  const candidates = [
    join(process.cwd(), 'node_modules', '.pnpm', '7zip-bin@5.2.0', 'node_modules', '7zip-bin', 'win', 'x64', '7za.exe'),
    join(process.cwd(), 'node_modules', '7zip-bin', 'win', 'x64', '7za.exe'),
  ];
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  // 通用搜索
  try {
    const result = execSync(
      'dir /s /b node_modules\\7za.exe 2>nul',
      { cwd: process.cwd(), encoding: 'utf8', timeout: 10000 }
    ).trim().split('\n');
    if (result.length > 0 && result[0]) return result[0].trim();
  } catch { /* ignore */ }
  return null;
}

function fixWinCodeSignCache() {
  const cacheRoot = join(
    homedir(),
    'AppData', 'Local', 'electron-builder', 'Cache', 'winCodeSign'
  );

  console.log(`\n🔧 扫描 winCodeSign 缓存: ${cacheRoot}`);

  if (!existsSync(cacheRoot)) {
    console.log('  缓存目录不存在，跳过');
    return;
  }

  const entries = readdirSync(cacheRoot, { withFileTypes: true });
  const sevenZFiles = entries.filter(e => e.isFile() && e.name.endsWith('.7z'));

  if (sevenZFiles.length === 0) {
    console.log('  未找到 .7z 文件，跳过');
    return;
  }

  const sevenZaPath = findSevenZaPath();
  if (!sevenZaPath) {
    console.log('  ⚠ 未找到 7za.exe');
    return;
  }
  console.log(`  使用 7za: ${sevenZaPath}`);

  for (const szFile of sevenZFiles) {
    const szPath = join(cacheRoot, szFile.name);
    const dirName = szFile.name.replace(/\.7z$/, '');
    const extractDir = join(cacheRoot, dirName);

    console.log(`\n📦 处理: ${szFile.name}`);

    // 如果目标目录已存在且包含 signtool.exe，跳过
    const signtoolPath = join(extractDir, 'windows-10', 'signtool.exe');
    if (existsSync(signtoolPath)) {
      console.log('  ✓ 缓存已就绪（signtool.exe 存在），跳过');
      continue;
    }

    // 创建目标目录
    if (!existsSync(extractDir)) {
      mkdirSync(extractDir, { recursive: true });
    }

    // 用 7za 解压，忽略 exit code 2
    runTolerant(`"${sevenZaPath}" x "${szPath}" -o"${extractDir}" -y`);

    // 创建 macOS dylib 占位文件
    const dylibDir = join(extractDir, 'darwin', '10.12', 'lib');
    for (const dylib of ['libcrypto.dylib', 'libssl.dylib']) {
      const dylibPath = join(dylibDir, dylib);
      if (!existsSync(dylibPath)) {
        mkdirSync(dylibDir, { recursive: true });
        writeFileSync(dylibPath, '');
        console.log(`  ✓ 创建占位文件: darwin/10.12/lib/${dylib}`);
      }
    }

    // 验证
    if (existsSync(signtoolPath)) {
      console.log('  ✓ 验证通过: signtool.exe 已就绪');
    } else {
      console.log('  ⚠ signtool.exe 不存在，解压可能不完整');
    }
  }
}

/* ── 主流程 ──────────────────────────────────────────── */

console.log('═══════════════════════════════════════════════');
console.log('  ReflexionOS Windows 打包');
console.log('═══════════════════════════════════════════════');

// 1) 构建前端
console.log('\n── 步骤 1/3: 构建前端 ──');
run('pnpm build');

// 2) 打包后端
console.log('\n── 步骤 2/3: 打包后端 ──');
run('pnpm package:backend');

// 3) 准备后端二进制
console.log('\n── 步骤 3/3: 准备后端二进制 ──');
run('pnpm prepare:backend-bin');

// 4) electron-builder
console.log('\n── 开始 electron-builder 打包 ──');
process.env.CSC_IDENTITY_AUTO_DISCOVERY = 'false';

try {
  run('electron-builder --win');
  console.log('\n✅ Windows 打包成功！');
  process.exit(0);
} catch {
  console.log('\n⚠ 首次打包失败，尝试修复 winCodeSign 缓存...');

  // 修复缓存
  fixWinCodeSignCache();

  // 重试
  console.log('\n── 重试 electron-builder 打包 ──');
  try {
    run('electron-builder --win');
    console.log('\n✅ Windows 打包成功！（修复缓存后重试）');
    process.exit(0);
  } catch {
    console.error('\n❌ 重试仍然失败，请检查上方错误信息');
    process.exit(1);
  }
}
