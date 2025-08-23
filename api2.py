# Re-create the same code into /mnt/data/script.py directly without referencing __file__

code = r'''from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
import asyncio

try:
    import httpx
    from fastapi import FastAPI, Query
    from fastapi.middleware.cors import CORSMiddleware
except Exception as e:
    raise SystemExit("Please install dependencies first: pip install fastapi uvicorn httpx pytz")

app = FastAPI(
    title="Pakistan Agro Data Aggregator (No-API-Key)",
    version="0.1.0",
    description=(
        "Aggregates cleaned agro-climatic and soil features from free public sources "
        "(Open-Meteo Archive + Soil Moisture, NASA POWER, ISRIC SoilGrids)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def today_yyyy_mm_dd() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def date_n_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")

async def fetch_json(client: httpx.AsyncClient, url: str, timeout_s: int = 30) -> Optional[Dict[str, Any]]:
    try:
        r = await client.get(url, timeout=timeout_s)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def safe_get(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur

def mean(values: List[Optional[float]]) -> Optional[float]:
    nums = [v for v in values if isinstance(v, (int, float))]
    return (sum(nums) / len(nums)) if nums else None

def sum_values(values: List[Optional[float]]) -> Optional[float]:
    nums = [v for v in values if isinstance(v, (int, float))]
    return sum(nums) if nums else None

async def get_open_meteo_archive(lat: float, lon: float, start: str, end: str) -> Dict[str, Any]:
    daily_vars = "precipitation_sum,et0_fao_evapotranspiration,temperature_2m_mean"
    url = (
        "https://archive-api.open-meteo.com/v1/era5"
        f"?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}"
        f"&daily={daily_vars}&timezone=auto"
    )
    async with httpx.AsyncClient() as client:
        data = await fetch_json(client, url)
    cleaned = {
        "source": "open-meteo-archive",
        "period": {"start": start, "end": end},
        "daily": [],
        "aggregates": {},
        "raw_ok": data is not None,
    }
    if not data:
        return cleaned

    daily = data.get("daily", {})
    times = daily.get("time", [])
    precip = daily.get("precipitation_sum", [])
    et0 = daily.get("et0_fao_evapotranspiration", [])
    tmean = daily.get("temperature_2m_mean", [])

    for i, t in enumerate(times):
        cleaned["daily"].append(
            {
                "date": t,
                "precipitation_mm": precip[i] if i < len(precip) else None,
                "et0_mm": et0[i] if i < len(et0) else None,
                "t_mean_c": tmean[i] if i < len(tmean) else None,
            }
        )

    cleaned["aggregates"] = {
        "total_precip_mm": sum_values(precip),
        "total_et0_mm": sum_values(et0),
        "avg_t_mean_c": mean(tmean),
        "days": len(times),
    }
    return cleaned

async def get_open_meteo_soil(lat: float, lon: float, start: str, end: str) -> Dict[str, Any]:
    hourly_vars = "soil_moisture_0_to_7cm,soil_temperature_0_to_7cm"
    url = (
        "https://archive-api.open-meteo.com/v1/era5"
        f"?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}"
        f"&hourly={hourly_vars}&timezone=auto"
    )
    async with httpx.AsyncClient() as client:
        data = await fetch_json(client, url)
    cleaned = {
        "source": "open-meteo-soil-archive",
        "period": {"start": start, "end": end},
        "latest": {},
        "aggregates": {},
        "raw_ok": data is not None,
    }
    if not data:
        return cleaned

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    sm = hourly.get("soil_moisture_0_to_7cm", [])
    st = hourly.get("soil_temperature_0_to_7cm", [])

    latest_sm = None
    latest_st = None
    latest_time = None
    for i in range(len(times) - 1, -1, -1):
        if latest_time is None and i < len(times):
            latest_time = times[i]
        if latest_sm is None and i < len(sm) and isinstance(sm[i], (int, float)):
            latest_sm = sm[i]
        if latest_st is None and i < len(st) and isinstance(st[i], (int, float)):
            latest_st = st[i]
        if latest_sm is not None and latest_st is not None:
            break

    cleaned["latest"] = {
        "time": latest_time,
        "soil_moisture_m3m3": latest_sm,
        "soil_temp_c": latest_st,
    }
    cleaned["aggregates"] = {
        "mean_soil_moisture_m3m3": mean(sm),
        "mean_soil_temp_c": mean(st),
        "obs_count": len(times),
    }
    return cleaned

async def get_nasa_power(lat: float, lon: float, start: str, end: str) -> Dict[str, Any]:
    params = "T2M,RH2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN"
    url = (
        "https://power.larc.nasa.gov/api/temporal/daily/point"
        f"?parameters={params}&community=AG&latitude={lat}&longitude={lon}"
        f"&start={start.replace('-', '')}&end={end.replace('-', '')}&format=JSON"
    )
    async with httpx.AsyncClient() as client:
        data = await fetch_json(client, url)
    cleaned = {
        "source": "nasa-power-daily",
        "period": {"start": start, "end": end},
        "aggregates": {},
        "raw_ok": data is not None,
    }
    if not data:
        return cleaned

    d = data.get("properties", {}).get("parameter", {})
    t2m = d.get("T2M", {})
    rh2m = d.get("RH2M", {})
    precip = d.get("PRECTOTCORR", {})
    sw = d.get("ALLSKY_SFC_SW_DWN", {})

    def vals(m: Dict[str, Any]) -> List[Optional[float]]:
        return [float(v) if v is not None else None for _, v in sorted(m.items())]

    cleaned["aggregates"] = {
        "avg_t2m_c": mean(vals(t2m)),
        "avg_rh2m_pct": mean(vals(rh2m)),
        "total_precip_mm": sum_values(vals(precip)),
        "avg_solar_kwh_m2_day": mean(vals(sw)),
        "days": len(t2m),
    }
    return cleaned

async def get_soilgrids(lat: float, lon: float) -> Dict[str, Any]:
    properties = ["phh2o", "ocd", "cec", "clay", "sand", "silt", "bdod"]
    depths = ["0-5cm", "5-15cm", "15-30cm", "30-60cm"]
    query = "&".join([f"property={p}" for p in properties]) + "&" + "&".join([f"depth={d}" for d in depths])
    url = f"https://rest.isric.org/soilgrids/v2.0/properties/query?lon={lon}&lat={lat}&{query}&value=mean"
    async with httpx.AsyncClient() as client:
        data = await fetch_json(client, url)

    cleaned = {
        "source": "isric-soilgrids-v2",
        "location": {"lat": lat, "lon": lon},
        "layers": [],
        "raw_ok": data is not None,
    }
    if not data:
        return cleaned

    def safe_get(d: Dict[str, Any], path: List[str], default=None):
        cur = d
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return default
        return cur

    layers = data.get("properties", {}).get("layers", [])
    depth_map: Dict[str, Dict[str, Any]] = {d: {"depth": d} for d in depths}

    for layer in layers:
        name = layer.get("name")
        for depth in layer.get("depths", []):
            d = depth.get("range")
            val = safe_get(depth, ["values", "mean"])
            if d in depth_map:
                if name in {"clay", "sand", "silt"} and isinstance(val, (int, float)):
                    val = val / 10.0  # g/kg to %
                depth_map[d][name] = val

    cleaned["layers"] = list(depth_map.values())
    return cleaned

@app.get("/health")
async def health():
    return {"ok": True, "time_utc": datetime.utcnow().isoformat() + "Z"}

@app.get("/aggregate")
async def aggregate(
    lat: float = Query(..., ge=-90, le=90, description="Latitude in decimal degrees"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude in decimal degrees"),
    days: int = Query(7, ge=1, le=60, description="Lookback window for climate aggregates"),
):
    def today_yyyy_mm_dd() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    def date_n_days_ago(n: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")

    end = today_yyyy_mm_dd()
    start = date_n_days_ago(days)

    results = await asyncio.gather(
        get_open_meteo_archive(lat, lon, start, end),
        get_open_meteo_soil(lat, lon, start, end),
        get_nasa_power(lat, lon, start, end),
        get_soilgrids(lat, lon),
    )

    om_archive, om_soil, nasa, soil = results

    def safe_get(d: Dict[str, Any], path: List[str], default=None):
        cur = d
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return default
        return cur

    features = {
        "location": {"lat": lat, "lon": lon},
        "period": {"start": start, "end": end},
        "climate": {
            "total_rain_mm": safe_get(om_archive, ["aggregates", "total_precip_mm"]),
            "total_et0_mm": safe_get(om_archive, ["aggregates", "total_et0_mm"]),
            "avg_temp_c": safe_get(om_archive, ["aggregates", "avg_t_mean_c"]),
            "avg_rh_pct": safe_get(nasa, ["aggregates", "avg_rh2m_pct"]),
            "avg_solar_kwh_m2_day": safe_get(nasa, ["aggregates", "avg_solar_kwh_m2_day"]),
        },
        "soil_state": {
            "latest_soil_moisture_m3m3": safe_get(om_soil, ["latest", "soil_moisture_m3m3"]),
            "latest_soil_temp_c": safe_get(om_soil, ["latest", "soil_temp_c"]),
            "mean_soil_moisture_m3m3": safe_get(om_soil, ["aggregates", "mean_soil_moisture_m3m3"]),
        },
        "soil_properties": soil.get("layers", []),
        "sources_ok": {
            "open_meteo_archive": om_archive.get("raw_ok", False),
            "open_meteo_soil": om_soil.get("raw_ok", False),
            "nasa_power": nasa.get("raw_ok", False),
            "soilgrids": soil.get("raw_ok", False),
        },
    }

    return {"features": features, "sources": {"open_meteo_archive": om_archive, "open_meteo_soil": om_soil, "nasa_power": nasa, "soilgrids": soil}}
'''
# with open('/mnt/data/script.py', 'w', encoding='utf-8') as f:
#     f.write(code)

print("Wrote single-file API to /mnt/data/script.py")
