import { useState } from "react"
import type { CreateRunResponse, Run, Task } from "./api"
import { EventFeed } from "./components/EventFeed"
import { FleetView } from "./components/FleetView"
import { KillButton } from "./components/KillButton"
import { StartRunForm } from "./components/StartRunForm"
import { useEventStream } from "./useEventStream"

function App() {
  const [run, setRun] = useState<Run | null>(null)
  const [task, setTask] = useState<Task | null>(null)
  const events = useEventStream(run?.id ?? null)

  function handleStarted(result: CreateRunResponse) {
    setRun(result.run)
    setTask(result.task)
  }

  return (
    <div className="mx-auto max-w-5xl p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Local AI — Agent Platform</h1>
        <p className="text-sm text-gray-500">Phase 1: fleet view, live events, kill switch.</p>
      </header>

      <div className="grid gap-6 md:grid-cols-2">
        <StartRunForm onStarted={handleStarted} />
        <FleetView />
      </div>

      {run && task && (
        <section className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">
          <h2 className="text-lg font-semibold">Current run</h2>
          <p className="text-sm">
            <span className="font-medium">{run.goal}</span>{" "}
            <span className="text-gray-500">({run.status})</span>
          </p>
          <KillButton task={task} onKilled={setTask} />
        </section>
      )}

      <EventFeed events={events} />
    </div>
  )
}

export default App
