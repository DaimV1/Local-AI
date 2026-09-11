import { useState } from "react"
import { killTask, type Task } from "../api"

const TERMINAL_STATUSES = new Set(["done", "failed", "cancelled"])

export function KillButton({
  task,
  onKilled,
}: {
  task: Task
  onKilled: (task: Task) => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [killing, setKilling] = useState(false)
  const disabled = killing || TERMINAL_STATUSES.has(task.status)

  async function handleClick() {
    setKilling(true)
    setError(null)
    try {
      const updated = await killTask(task.id)
      onKilled(updated)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setKilling(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => void handleClick()}
        disabled={disabled}
        className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
      >
        {killing ? "Killing…" : "Kill"}
      </button>
      <span className="text-sm text-gray-500">task status: {task.status}</span>
      {error && <span className="text-sm text-red-600">{error}</span>}
    </div>
  )
}
