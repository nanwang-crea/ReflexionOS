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
