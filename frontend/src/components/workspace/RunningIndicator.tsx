/**
 * 文件功能：运行中状态指示器组件
 * 文件描述：展示一个带动画进度条的“运行中”提示，支持嵌入在消息流中（inline）或作为顶部横条（header）两种布局
 * 核心逻辑：三条渐变动画条模拟加速度感的加载效果，通过 layout 参数切换外观与容器结构
 */
type RunningIndicatorLayout = 'header' | 'inline'

interface RunningIndicatorProps {
  label: string
  layout?: RunningIndicatorLayout
  rootDataAttr?: string
  barDataAttr?: string
}

/**
 * 函数名：buildDataAttr
 * 入参：
 *   - name (string | undefined): data 属性名，未提供时不生成属性
 *   - value (string): 属性值
 * 功能：构建可选的 data-* 属性对象，便于测试选择器定位元素
 * 运行逻辑：name 存在时返回 { [name]: value }，否则返回空对象
 * 出参：Record<string, string> - 可直接展开到 JSX 属性上的对象
 */
function buildDataAttr(name: string | undefined, value: string) {
  return name ? { [name]: value } : {}
}

/**
 * 组件名：RunningIndicator
 * 入参（props）：
 *   - label (string): 展示的状态文案（如“正在思考”“正在执行工具”）
 *   - layout ('header' | 'inline'，默认 'inline'): 布局形态，header 为顶部横条样式，inline 为消息流内嵌样式
 *   - rootDataAttr (string，可选): 根容器的 data 属性名，用于测试定位
 *   - barDataAttr (string，可选): 每条动画条的 data 属性名，用于测试定位
 * 作用/渲染逻辑：渲染三条错开动画延迟的渐变进度条，配合文案展示运行中状态；header 布局下额外展示“运行中”小标题
 * 返回值：JSX.Element - 运行中指示器
 */
export function RunningIndicator({
  label,
  layout = 'inline',
  rootDataAttr,
  barDataAttr,
}: RunningIndicatorProps) {
  const isHeader = layout === 'header'

  return (
    <div
      {...buildDataAttr(rootDataAttr, 'true')}
      className={
        isHeader
          ? 'border-b border-edge-subtle bg-accent/8 px-4 py-3'
          : 'mb-8 mx-auto flex w-full max-w-[920px] items-center gap-3 text-sm text-content-secondary'
      }
      aria-live="polite"
    >
      <div className={isHeader ? 'flex items-center gap-3' : 'contents'}>
        <div className="flex w-10 flex-col gap-1.5">
          {[1, 2, 3].map((index) => (
            <div
              key={index}
              {...buildDataAttr(barDataAttr, String(index))}
              className="relative h-1 overflow-hidden rounded-full bg-accent/20 ring-1 ring-accent/20"
            >
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-accent via-status-success to-accent-hover shadow-[0_0_14px_rgba(59,130,246,0.45)] animate-running-bar"
                style={{
                  width: `${52 + index * 12}%`,
                  animationDelay: `${(index - 1) * 0.16}s`,
                }}
              />
            </div>
          ))}
        </div>
        <div className="min-w-0">
          {isHeader && (
            <div className="text-[11px] uppercase tracking-[0.08em] text-accent">
              运行中
            </div>
          )}
          <div className={isHeader ? 'text-sm font-medium text-content-primary' : 'font-medium text-content-primary'}>
            {label}
          </div>
        </div>
      </div>
    </div>
  )
}
