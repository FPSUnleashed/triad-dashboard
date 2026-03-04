export type StepName = 'planner' | 'worker' | 'reviewer'

export type StepStatus = 'pending' | 'running' | 'paused' | 'passed' | 'failed' | 'blocked' | 'cancelled'

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
