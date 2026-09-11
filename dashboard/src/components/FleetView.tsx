import { useEffect, useState } from "react"
import { type Agent, listAgents } from "../api"

const POLL_INTERVAL_MS = 2000

const STATUS_COLOR: Record<string, string> = {
  idle: "bg-gray-400",
  working: "bg-emerald-500",
  paused: "bg-amber-500",
  dead: "bg-red-500",
}

export function FleetView() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const result = await listAgents()
        if (!cancelled) {
          setAgents(result)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError((err as Error).message)
      }
    }

    void poll()
    const interval = setInterval(() => void poll(), POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return (
    <section className="rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <h2 className="text-lg font-semibold mb-3">Fleet</h2>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {agents.length === 0 && !error && (
        <p className="text-sm text-gray-500">No agents yet — start a run to spin one up.</p>
      )}
      <ul className="space-y-2">
        {agents.map((agent) => (
          <li key={agent.id} className="flex items-center gap-2 text-sm">
            <span
              className={`inline-block h-2.5 w-2.5 rounded-full ${STATUS_COLOR[agent.status] ?? "bg-gray-400"}`}
              title={agent.status}
            />
            <span className="font-medium">{agent.name}</span>
            <span className="text-gray-500">
              {agent.role} · tier: {agent.tier}
            </span>
            <span className="ml-auto text-gray-500">{agent.status}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
