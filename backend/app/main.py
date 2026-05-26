from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import files, git, llm, projects, sessions, skills, websocket
from app.app_services import agent_service
from app.errors import AppError


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

@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    status_code = 400
    if exc.code == "not_found":
        status_code = 404
    elif exc.code == "security_error":
        status_code = 403
    return JSONResponse(
        status_code=status_code,
        content=exc.to_dict(),
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
app.include_router(files.router)
app.include_router(git.router)


@app.get("/")
async def root():
    return {
        "name": "ReflexionOS",
        "version": "0.1.0",
        "status": "running",
        "features": {"websocket": True, "native_tools": True, "streaming": True},
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
