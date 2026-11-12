import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# 로컬에선 .env를 읽고, Railway에선 Variables가 이미 들어 있음
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
FRONT_ORIGINS = [
    o.strip() for o in os.getenv("FRONT_ORIGINS", "").split(",") if o.strip()
]

sb = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

app = FastAPI(title="my-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONT_ORIGINS,
    # 내 컴퓨터의 아무 포트 + 내 Vercel 팀(jeju-ax)의 jeju-market 배포 주소(미리보기 포함)
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+|https://jeju-market(-[a-z0-9-]+)?-jeju-ax\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


class ItemIn(BaseModel):
    name: str

@app.get("/v")
def health():
    return {"status": "uuuuuuuu"}


class ItemIn(BaseModel):
    name: str


@app.get("/items")
def list_items():
    try:
        res = sb.table("items").select("*").order("id", desc=True).limit(50).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
    return res.data


@app.post("/items")
def create_item(item: ItemIn):
    try:
        res = sb.table("items").insert({"name": item.name}).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
    return res.data[0]


# ───────────────────────── 장바구니 (제주 마켓) ─────────────────────────
# 상품 목록은 서버가 가진다. 가격을 화면에서 받으면 조작될 수 있기 때문.
PRODUCTS = [
    {"id": "hallabong", "name": "한라봉 3kg", "price": 24000, "emoji": "🍊", "desc": "향긋하고 달콤한 제주 대표 감귤", "tag": "과일"},
    {"id": "gamgyul-choco", "name": "감귤 초콜릿", "price": 9800, "emoji": "🍫", "desc": "귤 향이 가득한 선물용 초콜릿", "tag": "간식"},
    {"id": "omegi", "name": "오메기떡 10입", "price": 15000, "emoji": "🍡", "desc": "쫄깃한 제주 전통 떡", "tag": "간식"},
    {"id": "heukdwaeji", "name": "흑돼지 오겹살 600g", "price": 32000, "emoji": "🥓", "desc": "육즙 가득 제주 흑돼지", "tag": "정육"},
    {"id": "galchi", "name": "제주 은갈치 2미", "price": 38000, "emoji": "🐟", "desc": "은빛 싱싱한 갈치 세트", "tag": "수산"},
    {"id": "green-tea", "name": "한라산 녹차 티백", "price": 12000, "emoji": "🍵", "desc": "깊고 부드러운 녹차 30입", "tag": "차"},
    {"id": "tangerine-juice", "name": "감귤 착즙주스 10병", "price": 19000, "emoji": "🧃", "desc": "100% 감귤 원액 착즙", "tag": "음료"},
    {"id": "dolhareubang", "name": "돌하르방 미니 피규어", "price": 7500, "emoji": "🗿", "desc": "제주 여행 기념 소품", "tag": "기념품"},
    {"id": "jeju-honey", "name": "제주 꿀 500g", "price": 18000, "emoji": "🍯", "desc": "제주 자연에서 채취한 순수 꿀", "tag": "식품"},
]
PRODUCT_MAP = {p["id"]: p for p in PRODUCTS}
MAX_QTY = 99


class CartAdd(BaseModel):
    product_id: str
    qty: int = Field(default=1, ge=1, le=MAX_QTY)


class CartQty(BaseModel):
    qty: int = Field(ge=1, le=MAX_QTY)


def _check_cart_id(cart_id: str):
    # 브라우저가 만든 랜덤 문자열(UUID 등)만 허용
    if not (8 <= len(cart_id) <= 64) or not all(c.isalnum() or c in "-_" for c in cart_id):
        raise HTTPException(status_code=400, detail="cart_id 형식이 올바르지 않습니다.")


def _cart_view(cart_id: str):
    try:
        rows = sb.table("cart_items").select("product_id, qty").eq("cart_id", cart_id).order("created_at").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
    items, total, count = [], 0, 0
    for r in rows:
        p = PRODUCT_MAP.get(r["product_id"])
        if not p:  # 판매 종료된 상품은 건너뜀
            continue
        line = p["price"] * r["qty"]
        items.append({**p, "qty": r["qty"], "line_total": line})
        total += line
        count += r["qty"]
    return {"cart_id": cart_id, "items": items, "total": total, "count": count}


@app.get("/products")
def list_products():
    return PRODUCTS


@app.get("/cart/{cart_id}")
def get_cart(cart_id: str):
    _check_cart_id(cart_id)
    return _cart_view(cart_id)


@app.post("/cart/{cart_id}/items")
def add_to_cart(cart_id: str, body: CartAdd):
    _check_cart_id(cart_id)
    if body.product_id not in PRODUCT_MAP:
        raise HTTPException(status_code=404, detail="없는 상품입니다.")
    try:
        cur = sb.table("cart_items").select("qty").eq("cart_id", cart_id).eq("product_id", body.product_id).execute().data
        qty = min(MAX_QTY, (cur[0]["qty"] if cur else 0) + body.qty)
        sb.table("cart_items").upsert(
            {"cart_id": cart_id, "product_id": body.product_id, "qty": qty},
            on_conflict="cart_id,product_id",
        ).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
    return _cart_view(cart_id)


@app.patch("/cart/{cart_id}/items/{product_id}")
def set_qty(cart_id: str, product_id: str, body: CartQty):
    _check_cart_id(cart_id)
    try:
        sb.table("cart_items").update({"qty": body.qty}).eq("cart_id", cart_id).eq("product_id", product_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
    return _cart_view(cart_id)


@app.delete("/cart/{cart_id}/items/{product_id}")
def remove_from_cart(cart_id: str, product_id: str):
    _check_cart_id(cart_id)
    try:
        sb.table("cart_items").delete().eq("cart_id", cart_id).eq("product_id", product_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
    return _cart_view(cart_id)


@app.delete("/cart/{cart_id}")
def clear_cart(cart_id: str):
    _check_cart_id(cart_id)
    try:
        sb.table("cart_items").delete().eq("cart_id", cart_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
    return _cart_view(cart_id)


# ───────────────────── 미세먼지 (에어코리아 공공데이터) ─────────────────────
# 서비스키는 서버(.env / Railway Variables)에만 두고, 브라우저에는 노출하지 않는다.
import asyncio
import time
from datetime import datetime

import httpx
from fastapi import Header

DATA_GO_KR_KEY = os.getenv("DATA_GO_KR_KEY", "").strip()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
SIDO_NAME = os.getenv("SIDO_NAME", "제주").strip()          # /air 기본 지역
COLLECT_MINUTES = int(os.getenv("COLLECT_MINUTES", "60") or 60)
AIR_URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"

# 에어코리아가 쓰는 시·도 이름 17개
ALL_SIDOS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
             "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
# 매 시간 DB에 저장할 시·도 (쉼표로 구분, 비우면 전국). 예: COLLECT_SIDOS=제주
COLLECT_SIDOS = [s.strip() for s in os.getenv("COLLECT_SIDOS", "").split(",") if s.strip()] or ALL_SIDOS

_air_cache = {}                       # {시도: {"at": 시각, "rows": [...]}}
_nat_cache = {"at": 0.0, "data": None}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _grade(v):
    return int(v) if v and str(v).isdigit() else None


async def fetch_air(sido=None):
    """공공데이터 API에서 한 시·도의 실시간 측정값을 가져와 필요한 항목만 정리한다."""
    sido = sido or SIDO_NAME
    if not DATA_GO_KR_KEY:
        raise HTTPException(status_code=500, detail="DATA_GO_KR_KEY 가 설정되지 않았습니다")
    params = {
        "serviceKey": DATA_GO_KR_KEY, "returnType": "json", "numOfRows": 500,
        "pageNo": 1, "sidoName": sido, "ver": "1.0",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(AIR_URL, params=params)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"공공데이터 서버 연결 실패: {type(e).__name__}: {e}")
    try:
        body = r.json()["response"]
        if body["header"]["resultCode"] != "00":
            raise ValueError(body["header"]["resultMsg"])
        items = body["body"]["items"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"공공데이터 응답 오류({sido}): {e}")
    return [{
        "station_name": it["stationName"],
        "sido_name": it.get("sidoName") or sido,
        "data_time": it["dataTime"],
        "pm10": _num(it.get("pm10Value")), "pm10_grade": _grade(it.get("pm10Grade")),
        "pm25": _num(it.get("pm25Value")), "pm25_grade": _grade(it.get("pm25Grade")),
        "o3": _num(it.get("o3Value")), "no2": _num(it.get("no2Value")),
        "co": _num(it.get("coValue")), "so2": _num(it.get("so2Value")),
        "khai": _num(it.get("khaiValue")), "khai_grade": _grade(it.get("khaiGrade")),
    } for it in items if it.get("stationName") and it.get("dataTime")]


def save_air(rows):
    """DB 저장. 같은 (시도, 측정소, 측정시각)은 덮어쓰기라서 중복되지 않는다.
    (측정소 이름은 시·도마다 겹칠 수 있다: 예 '중구' → 시도 이름까지 키에 포함)"""
    uniq = {(r["sido_name"], r["station_name"], r["data_time"]): r for r in rows}
    rows = list(uniq.values())
    for i in range(0, len(rows), 500):
        sb.table("air_quality").upsert(rows[i:i + 500], on_conflict="sido_name,station_name,data_time").execute()


def _check_sido(sido):
    if sido not in ALL_SIDOS:
        raise HTTPException(status_code=400, detail=f"시도 이름이 올바르지 않습니다: {', '.join(ALL_SIDOS)}")
    return sido


async def _rows_cached(sido, ttl=300):
    c = _air_cache.get(sido)
    if not c or time.time() - c["at"] > ttl or not c["rows"]:
        _air_cache[sido] = c = {"rows": await fetch_air(sido), "at": time.time()}
    return c["rows"]


@app.get("/air")
async def get_air(sido: str = ""):
    sido = _check_sido(sido or SIDO_NAME)
    rows = await _rows_cached(sido)        # 5분 캐시: 새로고침을 반복해도 공공데이터 호출을 아낀다
    saved = True
    try:
        await asyncio.to_thread(save_air, rows)
    except Exception:
        saved = False  # 테이블 미생성/제약조건 문제여도 화면 표시는 계속한다
    return {"sido": sido, "saved_to_db": saved, "items": rows}


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


@app.get("/air/national")
async def air_national():
    """전국 17개 시·도의 측정소 값을 한 번에: 시도별 평균 + 측정소 목록 (10분 캐시)."""
    if _nat_cache["data"] and time.time() - _nat_cache["at"] < 600:
        return _nat_cache["data"]
    sem = asyncio.Semaphore(4)            # 공공데이터 서버에 한꺼번에 몰리지 않게

    async def one(s):
        async with sem:
            try:
                return s, await _rows_cached(s, ttl=600)
            except HTTPException:
                return s, None

    results = await asyncio.gather(*[one(s) for s in ALL_SIDOS])
    sidos, all_rows = {}, []
    for s, rows in results:
        if rows is None:
            continue
        all_rows += rows
        sidos[s] = {
            "count": len(rows),
            "avg_pm10": _avg([r["pm10"] for r in rows]),
            "avg_pm25": _avg([r["pm25"] for r in rows]),
            "items": [{k: r[k] for k in ("station_name", "data_time", "pm10", "pm10_grade", "pm25", "pm25_grade")}
                      for r in rows],
        }
    if not sidos:
        raise HTTPException(status_code=502, detail="전국 데이터를 가져오지 못했습니다")
    saved = True
    try:
        await asyncio.to_thread(save_air, all_rows)
    except Exception:
        saved = False
    data = {"saved_to_db": saved, "sidos": sidos}
    _nat_cache.update(at=time.time(), data=data)
    return data


@app.post("/admin/collect")
async def collect(x_admin_token: str = Header(default="")):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="관리자 토큰이 올바르지 않습니다")
    total = 0
    for s in COLLECT_SIDOS:
        rows = await fetch_air(s)
        try:
            await asyncio.to_thread(save_air, rows)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
        total += len(rows)
    return {"saved": total, "sidos": COLLECT_SIDOS}


@app.get("/air/history/{station}")
def air_history(station: str, limit: int = 48, sido: str = ""):
    try:
        q = sb.table("air_quality").select("*").eq("station_name", station)
        if sido:
            q = q.eq("sido_name", sido)
        res = q.order("data_time", desc=True).limit(min(limit, 200)).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
    return res.data


# ───────────── 예측: DB에 쌓인 시계열로 선형회귀 (다음 시간 미세먼지) ─────────────
def linreg(xs, ys):
    """최소제곱법 y = a*x + b (라이브러리 없이 직접 계산). 점이 부족하면 None."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return a, my - a * mx


def _forecast_one(points, key, hours):
    """points: [(datetime, row)] 시간순. key 값으로 hours시간 뒤까지 예측."""
    pts = [(t, r[key]) for t, r in points if r.get(key) is not None]
    if len(pts) < 3:
        return None
    t0 = pts[0][0]
    xs = [(t - t0).total_seconds() / 3600 for t, _ in pts]
    ys = [v for _, v in pts]
    fit = linreg(xs, ys)
    if not fit:
        return None
    a, b = fit
    last = xs[-1]
    out = [max(0.0, round(a * (last + h) + b, 1)) for h in range(1, hours + 1)]
    return {"next": out, "slope_per_hour": round(a, 2), "points": len(pts)}


def _recent_rows(sido, max_rows=5000):
    """한 시·도의 최근 기록을 최신순으로 (Supabase는 한 번에 1000행까지라 나눠서 읽는다)."""
    rows, start = [], 0
    while len(rows) < max_rows:
        part = (sb.table("air_quality").select("station_name,data_time,pm10,pm25")
                .eq("sido_name", sido).order("data_time", desc=True)
                .range(start, start + 999).execute().data)
        rows += part
        if len(part) < 1000:
            break
        start += 1000
    return rows


@app.get("/air/forecast")
def air_forecast(hours: int = 3, window: int = 48, sido: str = ""):
    """측정소별 PM10/PM2.5 최근 window개 값에 선형회귀를 적용해 앞으로 hours시간을 예측."""
    sido = _check_sido(sido or SIDO_NAME)
    hours = max(1, min(hours, 12))
    try:
        rows = _recent_rows(sido)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
    by = {}
    for r in rows:
        try:
            t = datetime.strptime(r["data_time"], "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            continue
        by.setdefault(r["station_name"], []).append((t, r))
    result = {}
    for name, pts in by.items():
        pts.sort(key=lambda p: p[0])
        pts = pts[-max(3, min(window, 200)):]
        result[name] = {
            "history": [{"t": r["data_time"], "pm10": r["pm10"], "pm25": r["pm25"]} for _, r in pts],
            "pm10": _forecast_one(pts, "pm10", hours),
            "pm25": _forecast_one(pts, "pm25", hours),
        }
    return {"sido": sido, "hours": hours, "method": "linear_regression", "stations": result}


async def _collect_loop():
    while True:
        for s in COLLECT_SIDOS:
            try:
                await asyncio.to_thread(save_air, await fetch_air(s))
            except Exception:
                pass
            await asyncio.sleep(0.5)
        await asyncio.sleep(max(COLLECT_MINUTES, 1) * 60)


@app.on_event("startup")
async def _start_collector():
    if DATA_GO_KR_KEY:
        asyncio.create_task(_collect_loop())
