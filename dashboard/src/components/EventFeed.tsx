import type { DashboardEvent } from "../useEventStream"

const EVENT_COLOR: Record<string, string> = {
  task_failed: "text-red-600",
  budget_exceeded: "text-red-600",
  approval_requested: "text-amber-600",
  task_completed: "text-emerald-600",
  artifact_written: "text-emerald-600",
}

function summarize(event: DashboardEvent): string {
  const entries = Object.entries(event.payload)
  if (entries.length === 0) return ""
  return entries.map(([key, value]) => `${key}=${JSON.stringify(value)}`).join(" ")
}

export function EventFeed({ events }: { events: DashboardEvent[] }) {
  return (
    <section className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex-1 min-w-0">
      <h2 className="text-lg font-semibold mb-3">Live events</h2>
      {events.length === 0 && (
        <p className="text-sm text-gray-500">Start a run to see events arrive here.</p>
      )}
      <ol className="space-y-1 font-mono text-xs overflow-y-auto max-h-96">
        {events.map((event) => (
          <li key={event.seq} className="flex gap-2">
            <span className="text-gray-400 shrink-0">
              {new Date(event.ts).toLocaleTimeString()}
            </span>
            <span className={`font-semibold shrink-0 ${EVENT_COLOR[event.type] ?? ""}`}>
              {event.type}
            </span>
            <span className="text-gray-500 truncate">{summarize(event)}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
