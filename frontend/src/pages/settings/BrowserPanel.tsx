/**
 * BrowserPanel — 浏览器配置面板组件。
 *
 * 在 Settings 页面的"浏览器" tab 中展示，提供浏览器相关配置项的
 * 展示和编辑功能。配置通过 /api/ui-settings API 读写。
 *
 * 配置项：
 *   - headless: 是否无头模式
 *   - browser_engine: 浏览器引擎 (chromium/firefox/webkit)
 *   - default_timeout: 导航超时时间 (ms)
 *   - block_private_ips: 是否禁止访问私有 IP
 */

import { useEffect, useState } from 'react'
import { Globe, Monitor, Shield, Clock } from 'lucide-react'

/** 浏览器配置数据结构，与后端 BrowserSettings 模型对应 */
interface BrowserSettings {
  headless: boolean
  browser_engine: 'chromium' | 'firefox' | 'webkit'
  default_timeout: number
  default_wait_until: 'load' | 'domcontentloaded' | 'networkidle'
  block_private_ips: boolean
  blocked_url_patterns: string[]
}

/**
 * 浏览器配置面板组件。
 *
 * 执行逻辑：
 *   1. 组件挂载时从 GET /api/ui-settings 加载现有配置
 *   2. 用户修改配置项后更新本地 state
 *   3. 点击"保存配置"时将完整 ui-settings（含 browser 字段）PUT 回后端
 */
export function BrowserPanel() {
  /** 浏览器配置状态，初始化为默认值 */
  const [settings, setSettings] = useState<BrowserSettings>({
    headless: true,
    browser_engine: 'chromium',
    default_timeout: 30000,
    default_wait_until: 'load',
    block_private_ips: false,
    blocked_url_patterns: [],
  })

  /** 保存按钮的加载状态 */
  const [saving, setSaving] = useState(false)

  /**
   * 组件挂载时加载配置。
   * 从 /api/ui-settings 读取完整配置，提取 browser 字段设置到本地 state。
   */
  useEffect(() => {
    fetch('/api/ui-settings')
      .then(r => r.json())
      .then(data => {
        if (data.browser) setSettings(data.browser)
      })
      .catch(console.error)
  }, [])

  /**
   * 保存配置到后端。
   *
   * 执行逻辑：
   *   1. 先获取当前完整 ui-settings（避免覆盖其他配置）
   *   2. 合并 browser 字段
   *   3. PUT /api/ui-settings 提交
   */
  const save = async () => {
    setSaving(true)
    try {
      const current = await fetch('/api/ui-settings').then(r => r.json())
      await fetch('/api/ui-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...current, browser: settings }),
      })
    } catch (e) {
      console.error('Failed to save browser settings', e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-content-primary">浏览器配置</h3>

      <div className="space-y-4 rounded-lg border border-edge bg-surface-secondary p-4">
        {/* 无头模式开关 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Monitor className="h-4 w-4 text-content-secondary" />
            <span className="text-sm text-content-primary">无头模式</span>
          </div>
          <button
            onClick={() => setSettings(s => ({ ...s, headless: !s.headless }))}
            className={`relative h-6 w-11 rounded-full transition-colors ${settings.headless ? 'bg-accent' : 'bg-surface-tertiary'}`}
          >
            <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${settings.headless ? 'left-[22px]' : 'left-0.5'}`} />
          </button>
        </div>

        {/* 浏览器引擎选择 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Globe className="h-4 w-4 text-content-secondary" />
            <span className="text-sm text-content-primary">浏览器引擎</span>
          </div>
          <select
            value={settings.browser_engine}
            onChange={e => setSettings(s => ({ ...s, browser_engine: e.target.value as BrowserSettings['browser_engine'] }))}
            className="rounded border border-edge bg-surface-primary px-2 py-1 text-sm text-content-primary"
          >
            <option value="chromium">Chromium</option>
            <option value="firefox">Firefox</option>
            <option value="webkit">WebKit</option>
          </select>
        </div>

        {/* 导航超时设置 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-content-secondary" />
            <span className="text-sm text-content-primary">导航超时 (ms)</span>
          </div>
          <input
            type="number"
            value={settings.default_timeout}
            onChange={e => setSettings(s => ({ ...s, default_timeout: Number(e.target.value) }))}
            className="w-24 rounded border border-edge bg-surface-primary px-2 py-1 text-sm text-content-primary"
          />
        </div>

        {/* 私有 IP 限制开关 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-content-secondary" />
            <span className="text-sm text-content-primary">禁止私有 IP</span>
          </div>
          <button
            onClick={() => setSettings(s => ({ ...s, block_private_ips: !s.block_private_ips }))}
            className={`relative h-6 w-11 rounded-full transition-colors ${settings.block_private_ips ? 'bg-accent' : 'bg-surface-tertiary'}`}
          >
            <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${settings.block_private_ips ? 'left-[22px]' : 'left-0.5'}`} />
          </button>
        </div>
      </div>

      {/* 保存按钮 */}
      <button
        onClick={save}
        disabled={saving}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
      >
        {saving ? '保存中...' : '保存配置'}
      </button>
    </div>
  )
}
