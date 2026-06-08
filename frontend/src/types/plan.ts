export interface PlanStep {
  content: string
  status: 'pending' | 'in_progress' | 'completed' | 'blocked'
  findings: string
}

export interface Plan {
  goal: string
  steps: PlanStep[]
}
