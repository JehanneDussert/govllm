import httpx
from fastapi import APIRouter, HTTPException, Depends
from shared.config import get_observability_settings, ObservabilitySettings

router = APIRouter(prefix="/grafana", tags=["grafana"])


@router.get("/dashboard/{uid}")
async def get_dashboard(
    uid: str,
    settings: ObservabilitySettings = Depends(get_observability_settings),
):
    if not settings.grafana_service_token:
        raise HTTPException(status_code=503, detail="Grafana token not configured")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{settings.grafana_url}/api/dashboards/uid/{uid}",
            headers={"Authorization": f"Bearer {settings.grafana_service_token}"},
        )
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found")
    r.raise_for_status()
    return r.json()


@router.get("/embed-url/{uid}")
async def get_embed_url(
    uid: str,
    panel_id: int = 1,
    settings: ObservabilitySettings = Depends(get_observability_settings),
):
    url = f"{settings.grafana_url}/d-solo/{uid}?orgId=1&panelId={panel_id}&kiosk"
    return {"embed_url": url, "uid": uid, "panel_id": panel_id}
