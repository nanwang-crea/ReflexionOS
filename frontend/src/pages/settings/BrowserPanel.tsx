import { useEffect, useState } from 'react'
import { Globe, Monitor, Shield, Clock } from 'lucide-react'

interface BrowserSettings {
  headless: boolean
  browser_engine: 'chromium' | 'firefox' | 'webkit'
  default_timeout: number
  default_wait_until: 'load' | 'domcontentloaded' | 'networkidle'
  block_private_ips: boolean
  blocked_url_patterns: string[]
}

export function BrowserPanel() {
  const [settings, setSettings] = useState<BrowserSettings>({
    headless: true,
    browser_engine: 'chromium',
    default_timeout: 30000,
    default_wait_until: 'load',
    block_private_ips: false,
    blocked_url_patterns: [],
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch('/api/ui-settings')
      .then(r => r.json())
      .then(data => {
        if (data.browser) setSettings(data.browser)
      })
      .catch(console.error)
  }, [])

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
