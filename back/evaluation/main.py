# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.benchmark import router as benchmark_router
from routers.config import router as config_router
from routers.eval import router as eval_router
from routers.matrix import router as matrix_router
from routers.arena import router as arena_router
from routers.lifecycle import router as lifecycle_router
from routers.groundtruth import router as groundtruth_router
from shared.config import get_evaluation_settings
from db.database import run_migrations, close_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_evaluation_settings()

DRIFT_CHECK_INTERVAL_SECONDS = 900  # 15 minutes


async def _drift_watcher_loop():
    """Background task: checks production models for score drift every 15 minutes."""
    await asyncio.sleep(60)  # initial delay — let the app warm up
    while True:
        try:
            from services.lifecycle import check_drift
            quarantined = await check_drift()
            if quarantined:
                logger.warning(f"[drift_watcher] Quarantined: {quarantined}")
            else:
                logger.debug("[drift_watcher] No drift detected")
        except Exception as e:
            logger.error(f"[drift_watcher] Error: {e}")
        await asyncio.sleep(DRIFT_CHECK_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_migrations()
    drift_task = asyncio.create_task(_drift_watcher_loop())
    yield
    drift_task.cancel()
    try:
        await drift_task
    except asyncio.CancelledError:
        pass
    await close_pool()


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
app.include_router(arena_router)
app.include_router(lifecycle_router)
app.include_router(groundtruth_router)


@app.get("/health")
async def health():
    return {"service": "evaluation", "status": "ok"}
