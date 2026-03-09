export type StepName = 'planner' | 'worker' | 'reviewer'

export type StepStatus = 'pending' | 'running' | 'paused' | 'passed' | 'failed' | 'blocked' | 'cancelled'

export type PlannerTaskStepStatus = 'pending' | 'in_progress' | 'blocked' | 'done' | 'cancelled'

export interface Profile {
  id: number
  name: string
  planner_prompt: string
  worker_inject_prompt: string
  reviewer_inject_prompt: string
  created_at: string
  updated_at: string
}

export interface Run {
  id: number
  goal: string
  global_context: string
  last_done_thing: string
  status: 'pending' | 'running' | 'paused' | 'success' | 'failed' | 'blocked' | 'cancelled'
  profile_id: number
  profile_name?: string
  created_at: string
  updated_at: string
  duration_seconds?: number
  duration_formatted?: string
  elapsed_seconds?: number
  elapsed_formatted?: string
}

export interface RunStep {
  id: number
  run_id: number
  step_name: StepName
  attempt: number
  status: StepStatus
  input_payload: string
  output_payload: string | null
  error: string | null
  agent_context_id: string | null
  started_at: string
  ended_at: string | null
  duration_seconds?: number
  duration_formatted?: string
}

export interface RunEvent {
  id: number
  run_id: number
  level: 'info' | 'warn' | 'error'
  message: string
  meta: string | null
  created_at: string
}

export interface RunDetailResponse {
  run: Run
  is_running: boolean
  step_status: Record<StepName, Partial<RunStep> & { step_name: StepName; status: StepStatus }>
}

export interface PlannerTaskStep {
  id: number
  run_id: number
  position: number
  title: string
  status: PlannerTaskStepStatus
  details: string
  created_at: string
  updated_at: string
  completed_at: string | null
}

export interface PlannerTaskStateSummary {
  run_mode: 'fresh' | 'in_progress'
  state_title: string
  state_detail: string
  has_stored_task_steps: boolean
  total_stored_task_steps: number
  open_task_steps: number
  completed_task_steps: number
  cancelled_task_steps: number
  current_step_title: string | null
  current_step_status: PlannerTaskStepStatus | null
}

export interface PlannerTaskStateResponse extends PlannerTaskStateSummary {
  steps: PlannerTaskStep[]
}

export interface LoopState {
  auto_loop_enabled: boolean
  ok?: boolean
}

export interface StepStats {
  total_seconds: number
  total_formatted: string
  step_count: number
  avg_seconds: number
  avg_formatted: string
}

export interface Stats {
  total_runs: number
  status_counts: Record<string, number>
  step_stats: Record<StepName, StepStats>
  total_all_steps_seconds: number
  total_all_steps_formatted: string
}

export interface SystemMetrics {
  cpu_percent: number
  ram_used_gb: number
  ram_total_gb: number
  ram_percent: number
  vm_running: boolean
  vm_info: {
    pid?: number
    ram_alloc?: string
    kvm?: boolean
  }
}
