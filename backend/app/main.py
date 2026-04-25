from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import llm, projects, sessions, skills, websocket
from app.services.agent_service import agent_service


@asynccontextmanager
async def lifespan(_app: FastAPI):
    agent_service.start_background_tasks()
    try:
        yield
    finally:
        await agent_service.stop_background_tasks()

app = FastAPI(
    title="ReflexionOS",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(sessions.router)
app.include_router(llm.router)
app.include_router(skills.router)
app.include_router(websocket.router)


@app.get("/")
async def root():
    return {
        "name": "ReflexionOS",
        "version": "0.1.0",
        "status": "running",
        "features": {
            "websocket": True,
            "native_tools": True,
            "streaming": True
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
