from fastapi import FastAPI

from api.control import router as control_router
from api.events_stream import router as events_router

app = FastAPI(title="Local-AI control API")
app.include_router(control_router)
app.include_router(events_router)
