export interface PlanStep {
  id: number
  description: string
  status: 'pending' | 'in_progress' | 'completed' | 'blocked' | 'failed' | 'cancelled'
}

export interface Plan {
  goal: string
  steps: PlanStep[]
  currentStepIndex: number
}
