from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.control import router as control_router
from api.events_stream import router as events_router

app = FastAPI(title="Local-AI control API")

# Single local user, no auth (non-goal) — the dashboard runs on a
# different dev port than the API, so allow it without fighting CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(control_router)
app.include_router(events_router)
