import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.benchmark import router as benchmark_router
from routers.config import router as config_router
from routers.eval import router as eval_router
from routers.matrix import router as matrix_router
from services.redis_consumer import consume_events
from shared.schemas.events import LLMEvent
from shared.config import get_evaluation_settings

logging.basicConfig(level=logging.INFO)
settings = get_evaluation_settings()


async def handle_event(event: LLMEvent) -> None:
    """Handler appelé pour chaque event Redis reçu."""
    pass  # Scoring is triggered from the front end via a POST request to /eval/score 


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [asyncio.create_task(consume_events(handle_event))]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(
    title="LLM Evaluation",
    description="Judge configurable, scoring souverain, benchmark",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(benchmark_router)
app.include_router(config_router)
app.include_router(eval_router)
app.include_router(matrix_router)


@app.get("/health")
async def health():
    return {"service": "evaluation", "status": "ok"}