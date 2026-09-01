/**
 * 文件功能：设置页“聊天显示”选项面板组件
 * 文件描述：提供“过程内容默认展开”“完成后自动折叠过程”两个 UI 显示开关，配置持久化到后端 UI 设置接口
 * 核心逻辑：首次挂载时从 settings store 判断是否已加载过 UI 设置，未加载则请求接口并写入 store；
 *          切换开关时先调用后端更新接口，成功后再同步更新本地 store 状态
 */
import { useCallback, useEffect } from 'react'
import { uiSettingsApi } from '@/features/settings/api/uiSettings.api'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import { useToastStore } from '@/shared/stores/toast.store'

/**
 * 函数名：ToggleSwitch
 * 入参：
 *   - checked (boolean): 当前开关状态，true 为开启
 *   - onChange (() => void): 点击开关时触发的回调函数
 * 功能：渲染一个可复用的开关（toggle switch）UI 组件
 * 运行逻辑：根据 checked 值切换按钮和内部圆点的样式（背景色、位移），点击时调用 onChange
 * 出参：JSX.Element - 开关按钮的 DOM 结构
 */
function ToggleSwitch({
  checked,
  onChange,
}: {
  checked: boolean
  onChange: () => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 ${
        checked ? 'bg-accent' : 'bg-surface-tertiary'
      }`}
    >
      <span
        aria-hidden="true"
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
  )
}

/**
 * 函数名：DisplayOptionsPanel
 * 入参：无
 * 功能：渲染聊天显示相关的两个开关设置项，并处理其加载与保存逻辑
 * 运行逻辑：
 *   1. 从 settings store 中读取 showProcessExpanded、autoCollapseProcess 当前值及加载标记 uiSettingsLoaded
 *   2. 挂载时若尚未加载过 UI 设置，则调用 uiSettingsApi.get() 拉取并写入 store；失败时弹出错误提示
 *   3. handleToggle 负责切换指定开关：先计算新值，调用后端更新接口，成功后同步更新本地 store，失败则提示错误
 *   4. 渲染两个设置项区块，分别绑定 ToggleSwitch 组件和对应的说明文案
 * 出参：JSX.Element - 显示选项设置面板的 DOM 结构
 */
export function DisplayOptionsPanel() {
  const showProcessExpanded = useSettingsStore((s) => s.showProcessExpanded)
  const autoCollapseProcess = useSettingsStore((s) => s.autoCollapseProcess)
  const uiSettingsLoaded = useSettingsStore((s) => s.uiSettingsLoaded)
  const setUISetting = useSettingsStore((s) => s.setUISetting)

  /**
   * 函数名：useEffect（挂载时加载 UI 设置）
   * 入参：依赖 [uiSettingsLoaded, setUISetting]
   * 功能：在组件挂载且 UI 设置尚未加载过的情况下，从后端拉取显示设置并写入 store
   * 运行逻辑：若 uiSettingsLoaded 为 true 则直接跳过；否则调用 uiSettingsApi.get() 拉取数据，
   *          成功后将 show_process_expanded、auto_collapse_process 映射写入 store；失败则弹出错误 toast
   * 出参：无（副作用型 hook）
   */
  useEffect(() => {
    if (uiSettingsLoaded) return
    uiSettingsApi.get()
      .then((res) => {
        setUISetting({
          showProcessExpanded: res.data.show_process_expanded,
          autoCollapseProcess: res.data.auto_collapse_process,
        })
      })
      .catch(() => {
        useToastStore.getState().addToast('error', '加载 UI 设置失败')
      })
  }, [uiSettingsLoaded, setUISetting])

  /**
   * 函数名：handleToggle
   * 入参：
   *   - key ('show_process_expanded' | 'auto_collapse_process'): 需要切换的配置项键名
   * 功能：切换指定的显示配置项，并将新值持久化到后端
   * 运行逻辑：
   *   1. 根据 key 取出当前值，计算取反后的新值 next
   *   2. 调用 uiSettingsApi.update 提交两个字段的最新组合（未切换的字段保持原值）
   *   3. 提交成功后调用 setUISetting 同步更新本地 store
   *   4. 若请求失败，弹出错误提示，不更新本地状态
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新状态或提示错误）
   */
  const handleToggle = useCallback(async (key: 'show_process_expanded' | 'auto_collapse_process') => {
    const current = key === 'show_process_expanded'
      ? showProcessExpanded
      : autoCollapseProcess
    const next = !current
    try {
      await uiSettingsApi.update({
        show_process_expanded: key === 'show_process_expanded' ? next : showProcessExpanded,
        auto_collapse_process: key === 'auto_collapse_process' ? next : autoCollapseProcess,
      })
      setUISetting({
        showProcessExpanded: key === 'show_process_expanded' ? next : showProcessExpanded,
        autoCollapseProcess: key === 'auto_collapse_process' ? next : autoCollapseProcess,
      })
    } catch {
      useToastStore.getState().addToast('error', '保存 UI 设置失败')
    }
  }, [showProcessExpanded, autoCollapseProcess, setUISetting])

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-edge bg-surface-primary p-6">
        <h3 className="mb-4 text-lg font-semibold text-content-primary">聊天显示</h3>

        <div className="flex items-center justify-between">
          <div>
            <p className="text-content-secondary">过程内容默认展开</p>
            <p className="mt-1 text-sm text-content-muted">
              开启后，思考过程和过程说明的内容默认展开显示；关闭则只显示标题行
            </p>
          </div>
          <ToggleSwitch
            checked={showProcessExpanded}
            onChange={() => { void handleToggle('show_process_expanded') }}
          />
        </div>

        <hr className="my-5 border-edge" />

        <div className="flex items-center justify-between">
          <div>
            <p className="text-content-secondary">完成后自动折叠过程</p>
            <p className="mt-1 text-sm text-content-muted">
              开启后，AI 回答生成完毕时自动将思考、工具调用等过程区域整体折叠，点击「展开过程」可重新查看
            </p>
          </div>
          <ToggleSwitch
            checked={autoCollapseProcess}
            onChange={() => { void handleToggle('auto_collapse_process') }}
          />
        </div>
      </div>
    </div>
  )
}
