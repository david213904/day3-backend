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

import httpx
from fastapi import Header

DATA_GO_KR_KEY = os.getenv("DATA_GO_KR_KEY", "").strip()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
SIDO_NAME = os.getenv("SIDO_NAME", "제주").strip()
COLLECT_MINUTES = int(os.getenv("COLLECT_MINUTES", "60") or 60)
AIR_URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"
_air_cache = {"at": 0.0, "rows": []}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _grade(v):
    return int(v) if v and str(v).isdigit() else None


async def fetch_air():
    """공공데이터 API에서 시도별 실시간 측정값을 가져와 필요한 항목만 정리한다."""
    if not DATA_GO_KR_KEY:
        raise HTTPException(status_code=500, detail="DATA_GO_KR_KEY 가 설정되지 않았습니다")
    params = {
        "serviceKey": DATA_GO_KR_KEY, "returnType": "json", "numOfRows": 100,
        "pageNo": 1, "sidoName": SIDO_NAME, "ver": "1.0",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(AIR_URL, params=params)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"공공데이터 서버 연결 실패: {type(e).__name__}: {e}")
    try:
        body = r.json()["response"]
        if body["header"]["resultCode"] != "00":
            raise ValueError(body["header"]["resultMsg"])
        items = body["body"]["items"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"공공데이터 응답 오류: {e}")
    return [{
        "station_name": it["stationName"],
        "sido_name": it["sidoName"],
        "data_time": it["dataTime"],
        "pm10": _num(it.get("pm10Value")), "pm10_grade": _grade(it.get("pm10Grade")),
        "pm25": _num(it.get("pm25Value")), "pm25_grade": _grade(it.get("pm25Grade")),
        "o3": _num(it.get("o3Value")), "no2": _num(it.get("no2Value")),
        "co": _num(it.get("coValue")), "so2": _num(it.get("so2Value")),
        "khai": _num(it.get("khaiValue")), "khai_grade": _grade(it.get("khaiGrade")),
    } for it in items]


def save_air(rows):
    """DB 저장. 같은 (측정소, 측정시각)은 덮어쓰기라서 중복되지 않는다."""
    sb.table("air_quality").upsert(rows, on_conflict="station_name,data_time").execute()


@app.get("/air")
async def get_air():
    # 5분 캐시: 새로고침을 반복해도 공공데이터 호출 횟수를 아낀다
    if time.time() - _air_cache["at"] > 300 or not _air_cache["rows"]:
        _air_cache["rows"] = await fetch_air()
        _air_cache["at"] = time.time()
    saved = True
    try:
        await asyncio.to_thread(save_air, _air_cache["rows"])
    except Exception:
        saved = False  # 테이블 미생성/키 문제여도 화면 표시는 계속한다
    return {"sido": SIDO_NAME, "saved_to_db": saved, "items": _air_cache["rows"]}


@app.post("/admin/collect")
async def collect(x_admin_token: str = Header(default="")):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="관리자 토큰이 올바르지 않습니다")
    rows = await fetch_air()
    try:
        await asyncio.to_thread(save_air, rows)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
    return {"saved": len(rows)}


@app.get("/air/history/{station}")
def air_history(station: str, limit: int = 48):
    try:
        res = (sb.table("air_quality").select("*").eq("station_name", station)
               .order("data_time", desc=True).limit(min(limit, 200)).execute())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 오류: {e}")
    return res.data


async def _collect_loop():
    while True:
        try:
            await asyncio.to_thread(save_air, await fetch_air())
        except Exception:
            pass
        await asyncio.sleep(max(COLLECT_MINUTES, 1) * 60)


@app.on_event("startup")
async def _start_collector():
    if DATA_GO_KR_KEY:
        asyncio.create_task(_collect_loop())
