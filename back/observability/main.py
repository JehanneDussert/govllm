from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.metrics import router as metrics_router
from routers.traces import router as traces_router
from routers.grafana import router as grafana_router
from shared.config import get_observability_settings

settings = get_observability_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="LLM Observability",
    description="Métriques Prometheus, traces Langfuse, proxy Grafana",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics_router)
app.include_router(traces_router)
app.include_router(grafana_router)


@app.get("/health")
async def health():
    return {"service": "observability", "status": "ok"}