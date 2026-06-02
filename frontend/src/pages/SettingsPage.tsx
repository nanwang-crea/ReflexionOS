import { useState } from 'react'
import { Cpu, Eye, Info, Server } from 'lucide-react'
import { ProviderPanel } from './settings/ProviderPanel'
import { DefaultModelPanel } from './settings/DefaultModelPanel'
import { DisplayOptionsPanel } from './settings/DisplayOptionsPanel'
import { AboutPanel } from './settings/AboutPanel'

type SettingsTab = 'providers' | 'default-model' | 'display' | 'about'

const tabs: Array<{ key: SettingsTab; label: string; icon: typeof Server }> = [
  { key: 'providers', label: '模型供应商', icon: Server },
  { key: 'default-model', label: '默认模型', icon: Cpu },
  { key: 'display', label: '显示选项', icon: Eye },
  { key: 'about', label: '关于', icon: Info },
]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('providers')

  return (
    <div className="flex h-full flex-col bg-surface-primary md:flex-row">
      <nav className="shrink-0 border-b border-edge bg-surface-secondary p-3 md:w-56 md:border-b-0 md:border-r md:p-4">
        <h2 className="mb-3 px-3 text-xl font-bold text-content-primary md:mb-4">设置</h2>
        <ul className="flex gap-1 overflow-x-auto md:block md:space-y-1 md:overflow-visible">
          {tabs.map((tab) => {
            const Icon = tab.icon
            const active = activeTab === tab.key
            return (
              <li key={tab.key}>
                <button
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                  className={`flex whitespace-nowrap items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[15px] transition md:w-full ${
                    active
                      ? 'bg-surface-tertiary text-content-primary font-medium'
                      : 'text-content-secondary hover:bg-surface-tertiary'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span>{tab.label}</span>
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 md:px-8 md:py-8">
          {activeTab === 'providers' && <ProviderPanel />}
          {activeTab === 'default-model' && <DefaultModelPanel />}
          {activeTab === 'display' && <DisplayOptionsPanel />}
          {activeTab === 'about' && <AboutPanel />}
        </div>
      </div>
    </div>
  )
}
