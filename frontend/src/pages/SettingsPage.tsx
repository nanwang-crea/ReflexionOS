/**
 * 文件功能：设置页容器组件
 * 文件描述：提供设置页整体布局（左侧 Tab 导航 + 右侧内容区），根据当前选中的 Tab 渲染对应子面板
 *          （模型供应商/默认模型/显示选项/浏览器/关于）
 * 核心逻辑：使用本地 state 维护当前激活的 Tab，点击导航项切换 activeTab，并据此条件渲染对应的子面板组件
 */
import { useState } from 'react'
import { Cpu, Eye, Globe, Info, Server } from 'lucide-react'
import { ProviderPanel } from './settings/ProviderPanel'
import { DefaultModelPanel } from './settings/DefaultModelPanel'
import { DisplayOptionsPanel } from './settings/DisplayOptionsPanel'
import { AboutPanel } from './settings/AboutPanel'
import { BrowserPanel } from './settings/BrowserPanel'

/** 设置页 Tab 的联合类型，对应左侧导航中的各个选项 */
type SettingsTab = 'providers' | 'default-model' | 'display' | 'browser' | 'about'

/** 设置页 Tab 导航配置列表：每项包含唯一 key、显示文案和对应图标组件 */
const tabs: Array<{ key: SettingsTab; label: string; icon: typeof Server }> = [
  { key: 'providers', label: '模型供应商', icon: Server },
  { key: 'default-model', label: '默认模型', icon: Cpu },
  { key: 'display', label: '显示选项', icon: Eye },
  { key: 'browser', label: '浏览器', icon: Globe },
  { key: 'about', label: '关于', icon: Info },
]

/**
 * 函数名：SettingsPage
 * 入参：无
 * 功能：渲染设置页整体框架，包括左侧 Tab 导航栏和右侧对应的设置子面板
 * 运行逻辑：
 *   1. 使用 useState 维护当前激活的 Tab（默认 'providers'）
 *   2. 遍历 tabs 配置渲染导航按钮，点击时更新 activeTab
 *   3. 根据 activeTab 的值条件渲染 ProviderPanel / DefaultModelPanel / DisplayOptionsPanel /
 *      BrowserPanel / AboutPanel 中的一个
 * 出参：JSX.Element - 设置页整体的 DOM 结构
 */
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
          {activeTab === 'browser' && <BrowserPanel />}
          {activeTab === 'about' && <AboutPanel />}
        </div>
      </div>
    </div>
  )
}
