export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"

export interface Budget {
  max_steps: number | null
  max_tokens: number | null
  max_wallclock_seconds: number | null
  max_revision_rounds: number | null
}

export interface Run {
  id: string
  goal: string
  status: string
  created_by: string
  budget: Budget
  started_at: string | null
  finished_at: string | null
  workspace_path: string
  git_branch: string | null
}

export interface TaskSpec {
  role: string
  instructions: string
  context: Record<string, unknown>
  notes: string | null
}

export interface TaskResult {
  summary: string
  artifact_ids: string[]
  notes: string | null
}

export interface Task {
  id: string
  run_id: string
  parent_task_id: string | null
  group_id: string | null
  title: string
  spec: TaskSpec
  status: string
  claimed_by: string | null
  attempt: number
  budget_remaining: Budget
  result: TaskResult | null
  created_at: string
  updated_at: string
}

export interface Agent {
  id: string
  name: string
  role: string
  tier: string
  tool_allowlist: string[]
  status: string
  last_heartbeat: string | null
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface CreateRunResponse {
  run: Run
  task: Task
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!response.ok) {
    const body = await response.text()
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${response.status} ${body}`)
  }
  return response.json() as Promise<T>
}

export function createRun(goal: string, instructions: string): Promise<CreateRunResponse> {
  return request<CreateRunResponse>("/runs", {
    method: "POST",
    body: JSON.stringify({ goal, instructions }),
  })
}

export function killTask(taskId: string): Promise<Task> {
  return request<Task>(`/tasks/${taskId}/kill`, { method: "POST" })
}

export function listAgents(): Promise<Agent[]> {
  return request<Agent[]>("/agents")
}

export function listRunTasks(runId: string): Promise<Task[]> {
  return request<Task[]>(`/runs/${runId}/tasks`)
}
