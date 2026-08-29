/**
 * 文件功能：设置页“关于”面板组件
 * 文件描述：在设置页展示 ReflexionOS 的简介和版本号，纯静态展示，不涉及任何数据请求
 * 核心逻辑：直接渲染固定文案，无状态、无副作用
 */

/**
 * 函数名：AboutPanel
 * 入参：无
 * 功能：渲染“关于 ReflexionOS”的静态说明卡片
 * 运行逻辑：直接返回固定的介绍文本和版本号 JSX 结构，无任何交互逻辑
 * 出参：JSX.Element - 关于面板的 DOM 结构
 */
export function AboutPanel() {
  return (
    <div className="rounded-lg border border-edge bg-surface-primary p-6">
      <h3 className="mb-4 text-lg font-semibold text-content-primary">关于 ReflexionOS</h3>
      <p className="text-content-secondary">
        ReflexionOS 是一个 AI-powered coding agent，支持多供应商实例管理、
        默认模型配置、对话上下文压缩、工具审批等能力。
      </p>
      <p className="mt-2 text-sm text-content-muted">Version 0.1.0</p>
    </div>
  )
}
