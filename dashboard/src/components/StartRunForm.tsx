import { type FormEvent, useState } from "react"
import { createRun, type CreateRunResponse } from "../api"

export function StartRunForm({ onStarted }: { onStarted: (result: CreateRunResponse) => void }) {
  const [goal, setGoal] = useState("")
  const [instructions, setInstructions] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const result = await createRun(goal, instructions)
      onStarted(result)
      setGoal("")
      setInstructions("")
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form
      onSubmit={(event) => void handleSubmit(event)}
      className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3"
    >
      <h2 className="text-lg font-semibold">Start a task</h2>
      <div>
        <label className="block text-sm font-medium mb-1" htmlFor="goal">
          Goal
        </label>
        <input
          id="goal"
          required
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          className="w-full rounded border border-gray-300 dark:border-gray-600 bg-transparent px-2 py-1 text-sm"
          placeholder="write a one-line README"
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1" htmlFor="instructions">
          Instructions
        </label>
        <textarea
          id="instructions"
          required
          value={instructions}
          onChange={(event) => setInstructions(event.target.value)}
          className="w-full rounded border border-gray-300 dark:border-gray-600 bg-transparent px-2 py-1 text-sm"
          rows={3}
          placeholder="Write a single sentence describing this project."
        />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button
        type="submit"
        disabled={submitting}
        className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
      >
        {submitting ? "Starting…" : "Start"}
      </button>
    </form>
  )
}
