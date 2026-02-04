# api/osm_overpass.py
from __future__ import annotations

import os
import time
import random
import logging
from typing import Iterator, Dict, Any, List, Tuple

import requests

logger = logging.getLogger(__name__)

# 여러 인스턴스 로테이션
DEFAULT_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OVERPASS_URLS: List[str] = [
    x.strip() for x in os.getenv("OSM_OVERPASS_URLS", "").split(",") if x.strip()
] or DEFAULT_URLS

DEFAULT_UA = os.getenv("OSM_HTTP_USER_AGENT", "job-crawler/1.0 (+contact: you@example.com)")

# 요청 간 휴식(초) — 공격적으로 줄이면 오히려 실패↑
REQUEST_SLEEP_SEC = float(os.getenv("OSM_REQUEST_SLEEP_SEC", "2.0"))

# HTTP read timeout(초)
HTTP_TIMEOUT_SEC = int(os.getenv("OSM_HTTP_TIMEOUT_SEC", "240"))

# overpass QL timeout(초) — 너무 크게 잡으면 reverse proxy 504 가능성이 오히려 커질 수 있어 적당히
OVERPASS_QL_TIMEOUT = int(os.getenv("OSM_OVERPASS_QL_TIMEOUT", "180"))

# 타일 기본 크기(도 단위). 서울은 0.12~0.08 정도면 충분.
DEFAULT_TILE_DEG = float(os.getenv("OSM_TILE_DEG", "0.12"))
MIN_TILE_DEG = float(os.getenv("OSM_TILE_MIN_DEG", "0.03"))

_RELATION_CACHE: dict[str, int] = {}


def _post_overpass(query: str, timeout: int | None = None, retries: int = 4) -> dict:
    """
    - 429/502/503/504 및 timeout은 재시도
    - 인스턴스 로테이션
    - 지터(jitter) 포함 백오프
    """
    headers = {"User-Agent": DEFAULT_UA, "Accept": "application/json"}
    timeout = timeout or HTTP_TIMEOUT_SEC

    last_err = None
    for attempt in range(1, retries + 1):
        url = OVERPASS_URLS[(attempt - 1) % len(OVERPASS_URLS)]
        try:
            r = requests.post(url, data={"data": query}, headers=headers, timeout=timeout)
            if r.status_code in (429, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code} {r.reason}", response=r)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            # 지터 포함 지수 백오프 (최대 30초)
            base = min(30.0, (2 ** (attempt - 1)) * REQUEST_SLEEP_SEC)
            sleep_s = base * (0.8 + random.random() * 0.6)
            logger.warning(
                "Overpass request failed (attempt=%s/%s) url=%s: %s; sleep %.1fs",
                attempt, retries, url, e, sleep_s
            )
            time.sleep(sleep_s)

    raise RuntimeError(f"Overpass request failed after retries: {last_err}")


def _resolve_admin_relation_id(region_name: str, admin_level: str = "4") -> int:
    region_name = (region_name or "").strip()
    if not region_name:
        raise ValueError("region_name is empty")

    if region_name in _RELATION_CACHE:
        return _RELATION_CACHE[region_name]

    q = f"""
[out:json][timeout:60];
rel["boundary"="administrative"]["admin_level"="{admin_level}"]["name"="{region_name}"];
out ids;
""".strip()
    data = _post_overpass(q, timeout=120, retries=3)
    elems = data.get("elements") or []
    if elems:
        rel_id = int(elems[0]["id"])
        _RELATION_CACHE[region_name] = rel_id
        return rel_id

    # fallback: admin_level 없이 한번 더
    q2 = f"""
[out:json][timeout:60];
rel["boundary"="administrative"]["name"="{region_name}"];
out ids;
""".strip()
    data2 = _post_overpass(q2, timeout=120, retries=3)
    elems2 = data2.get("elements") or []
    if elems2:
        rel_id = int(elems2[0]["id"])
        _RELATION_CACHE[region_name] = rel_id
        return rel_id

    raise RuntimeError(f"Could not resolve admin relation id for region='{region_name}'")


def _area_id_from_relation_id(rel_id: int) -> int:
    return 3600000000 + int(rel_id)


def _relation_bounds(rel_id: int) -> Tuple[float, float, float, float]:
    """
    Overpass에서 relation의 bbox를 가져온다(out bb).
    """
    q = f"""
[out:json][timeout:60];
rel({int(rel_id)});
out bb;
""".strip()
    data = _post_overpass(q, timeout=120, retries=3)
    elems = data.get("elements") or []
    if not elems:
        raise RuntimeError(f"Could not fetch bounds for relation id={rel_id}")

    b = elems[0].get("bounds")
    if not b:
        raise RuntimeError(f"Relation has no bounds id={rel_id}")

    return float(b["minlat"]), float(b["minlon"]), float(b["maxlat"]), float(b["maxlon"])


def _tile_bounds(minlat: float, minlon: float, maxlat: float, maxlon: float, tile_deg: float) -> List[Tuple[float, float, float, float]]:
    tiles = []
    lat = minlat
    while lat < maxlat:
        next_lat = min(lat + tile_deg, maxlat)
        lon = minlon
        while lon < maxlon:
            next_lon = min(lon + tile_deg, maxlon)
            tiles.append((lat, lon, next_lat, next_lon))
            lon = next_lon
        lat = next_lat
    return tiles


def _extract_center(element: dict) -> tuple[float | None, float | None]:
    if "lat" in element and "lon" in element:
        return element.get("lat"), element.get("lon")
    center = element.get("center") or {}
    return center.get("lat"), center.get("lon")


def _pick_website(tags: dict) -> str | None:
    for k in ("contact:website", "website", "url", "contact:url", "contact:homepage"):
        v = tags.get(k)
        if v and isinstance(v, str):
            v = v.strip()
            if v:
                if not (v.startswith("http://") or v.startswith("https://")):
                    v = "https://" + v
                return v
    return None


def _selectors(mode: str, website_key: str, bbox: tuple[float, float, float, float] | None) -> list[str]:
    """
    NOTE:
    - 기존과 동일한 후보 로직 유지.
    - bbox가 주어지면 nwr(area.a)(bbox)로 "같은 area 조건 + bbox로만 분할" (품질 변화 최소)
    """
    bbox_part = ""
    if bbox:
        s, w, n, e = bbox
        bbox_part = f"({s},{w},{n},{e})"

    def base(expr: str) -> str:
        # expr 예: ["office"]["office"!="government"] ...
        return f'nwr(area.a){bbox_part}["{website_key}"]{expr};'

    if mode == "wide":
        return [
            base('["office"]["office"!="government"]["office"!="estate_agent"]'),
            base('["shop"]["shop"!="real_estate"]'),
            base('["industrial"]'),
            base('["manufacturing"]'),
            base('["man_made"="works"]'),
            base('["craft"]'),
        ]

    if mode == "narrow":
        return [
            base('["office"="it"]'),
            base('["shop"~"^(electronics|computer)$"]'),
            base('["industrial"~"^(electronics|manufacturing|machine_shop)$"]'),
            base('["man_made"="works"]'),
            base('["craft"="electronics"]'),
        ]

    # medium (현 상태 유지)
    return [
        base('["office"~"^(it|research|telecommunication|company)$"]["office"!="government"]["office"!="estate_agent"]'),
        base('["shop"~"^(electronics|computer|mobile_phone)$"]["shop"!="real_estate"]'),
        base('["industrial"]'),
        base('["manufacturing"]'),
        base('["man_made"="works"]'),
        base('["craft"]'),
    ]


def _build_query(area_id: int, mode: str, bbox: tuple[float, float, float, float] | None = None) -> str:
    selectors = []
    for website_key in ("website", "contact:website", "url"):
        selectors.extend(_selectors(mode, website_key, bbox=bbox))

    union = "\n  ".join(selectors)

    return f"""
[out:json][timeout:{OVERPASS_QL_TIMEOUT}];
area({area_id})->.a;
(
  {union}
);
out tags qt;
""".strip()


def _iter_elements_to_records(elements: list, limit: int | None = None) -> Iterator[Dict[str, Any]]:
    seen = 0
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("name:ko") or tags.get("operator")
        if not name:
            continue

        website = _pick_website(tags)
        lat, lon = _extract_center(el)

        yield {
            "name": name,
            "website": website,
            "lat": lat,
            "lon": lon,
            "osm_type": el.get("type"),
            "osm_id": el.get("id"),
            "tags": tags,
        }

        seen += 1
        if limit and seen >= int(limit):
            break


def iter_region_records(region_name: str, mode: str = "medium", tile_deg: float | None = None, limit: int | None = None) -> Iterator[Dict[str, Any]]:
    """
    타임아웃 완화 핵심:
    1) area 기반 단일 쿼리 먼저 시도 (기존과 동일)
    2) 실패하면 relation bbox를 tile로 쪼개서 area+bbox로 재시도 (결과 범위 변화 최소)
    """
    region_name = (region_name or "").strip()
    if not region_name:
        return

    rel_id = _resolve_admin_relation_id(region_name, admin_level="4")
    area_id = _area_id_from_relation_id(rel_id)

    tile_deg = float(tile_deg or DEFAULT_TILE_DEG)

    # 1) 단일 쿼리(기존 방식)
    time.sleep(REQUEST_SLEEP_SEC)
    q = _build_query(area_id, mode=mode, bbox=None)
    try:
        data = _post_overpass(q, timeout=HTTP_TIMEOUT_SEC, retries=4)
        elements = data.get("elements") or []
        yield from _iter_elements_to_records(elements, limit=limit)
        return
    except Exception as e:
        logger.warning("Area query failed region=%s mode=%s err=%s -> fallback to tiled bbox", region_name, mode, e)

    # 2) 실패 시 타일 fallback
    minlat, minlon, maxlat, maxlon = _relation_bounds(rel_id)
    tiles = _tile_bounds(minlat, minlon, maxlat, maxlon, tile_deg)

    seen_keys = set()
    yielded = 0

    def emit_from_elements(elements: list):
        nonlocal yielded
        for rec in _iter_elements_to_records(elements, limit=None):
            key = (rec.get("osm_type"), rec.get("osm_id"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            yield rec
            yielded += 1
            if limit and yielded >= int(limit):
                return

    for idx, bbox in enumerate(tiles, start=1):
        if limit and yielded >= int(limit):
            break

        # 너무 빡빡하게 때리지 않게 슬립
        time.sleep(REQUEST_SLEEP_SEC)

        q_tile = _build_query(area_id, mode=mode, bbox=bbox)
        try:
            data_t = _post_overpass(q_tile, timeout=HTTP_TIMEOUT_SEC, retries=4)
            elements_t = data_t.get("elements") or []
            for rec in emit_from_elements(elements_t):
                yield rec
                if limit and yielded >= int(limit):
                    break
        except Exception as e:
            # 타일도 실패하면 더 작은 타일로 한 번 더(적응형)
            if tile_deg > MIN_TILE_DEG:
                smaller = max(MIN_TILE_DEG, tile_deg / 2.0)
                logger.warning(
                    "Tile query failed idx=%s/%s bbox=%s err=%s -> retry with smaller tile_deg=%.4f",
                    idx, len(tiles), bbox, e, smaller
                )
                s, w, n, ee = bbox
                subtiles = _tile_bounds(s, w, n, ee, smaller)
                for sb in subtiles:
                    if limit and yielded >= int(limit):
                        break
                    time.sleep(REQUEST_SLEEP_SEC)
                    try:
                        data_s = _post_overpass(_build_query(area_id, mode=mode, bbox=sb), timeout=HTTP_TIMEOUT_SEC, retries=3)
                        els_s = data_s.get("elements") or []
                        for rec in emit_from_elements(els_s):
                            yield rec
                            if limit and yielded >= int(limit):
                                break
                    except Exception as e2:
                        logger.warning("Subtile failed bbox=%s err=%s (skip)", sb, e2)
                        continue
            else:
                logger.warning("Tile query failed idx=%s/%s bbox=%s err=%s (skip)", idx, len(tiles), bbox, e)
                continue
