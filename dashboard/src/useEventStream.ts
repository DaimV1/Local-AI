import { useEffect, useState } from "react"
import { API_BASE_URL } from "./api"

export interface DashboardEvent {
  seq: number
  run_id: string
  task_id: string | null
  agent_id: string | null
  type: string
  payload: Record<string, unknown>
  ts: string
}

/**
 * The dashboard's only source of live state (design rule 5): it reads
 * nothing but this event stream, never polling an agent directly.
 */
export function useEventStream(runId: string | null): DashboardEvent[] {
  const [events, setEvents] = useState<DashboardEvent[]>([])
  const [trackedRunId, setTrackedRunId] = useState(runId)

  // Reset during render when the run changes, rather than in the effect
  // below — the officially recommended way to adjust state on a prop
  // change without an extra cascading render.
  if (runId !== trackedRunId) {
    setTrackedRunId(runId)
    setEvents([])
  }

  useEffect(() => {
    if (!runId) {
      return
    }

    const source = new EventSource(`${API_BASE_URL}/runs/${runId}/events/stream`)
    source.onmessage = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as DashboardEvent
      setEvents((prev) => [...prev, event])
    }

    return () => source.close()
  }, [runId])

  return events
}
