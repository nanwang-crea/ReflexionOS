export interface ExecutionStep {
  id: string
  step_number: number
  tool: string
  args: Record<string, any>
  status: 'pending' | 'running' | 'success' | 'failed'
  output?: string
  error?: string
  duration?: number
  timestamp: string
}

export interface Execution {
  id: string
  project_id: string
  task: string
  provider_id?: string
  model_id?: string
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'
  steps: ExecutionStep[]
  result?: string
  total_duration?: number
  created_at: string
  completed_at?: string
}

export interface ExecutionCreate {
  project_id: string
  task: string
  provider_id?: string
  model_id?: string
}
