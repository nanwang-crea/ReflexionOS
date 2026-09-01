// 文件功能：Agent 执行计划（Plan）相关类型定义
// 文件描述：定义计划步骤与计划整体的结构，用于展示 Agent 在 plan 模式下生成的执行计划及各步骤进展
// 核心逻辑：一个 Plan 包含一个目标（goal）和若干有序步骤（steps），每个步骤有独立的状态和执行发现
export interface PlanStep {
  content: string // 步骤内容描述
  status: 'pending' | 'in_progress' | 'completed' | 'blocked' // 步骤状态：待处理/进行中/已完成/被阻塞
  findings: string // 该步骤执行过程中产生的发现/结论说明
}

// 执行计划：包含总体目标及分解出的若干步骤
export interface Plan {
  goal: string // 计划的总体目标
  steps: PlanStep[]
}
