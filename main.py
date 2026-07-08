from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from collections import defaultdict, deque
import time
import uuid
import base64

app = FastAPI()

# Assigned values
TOTAL_ORDERS = 52
RATE_LIMIT = 16
WINDOW_SECONDS = 10

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Idempotency storage
# -------------------------

idempotency_store = {}

# -------------------------
# Rate limiting storage
# -------------------------

client_requests = defaultdict(deque)

# -------------------------
# Fixed catalog orders
# IDs 1..52
# -------------------------

ORDERS = [
    {
        "id": i,
        "item": f"order-{i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]


# -------------------------
# Rate limit middleware
# -------------------------

@app.middleware("http")
async def rate_limit(request: Request, call_next):

    client_id = request.headers.get("X-Client-Id")

    if client_id:
        now = time.time()
        bucket = client_requests[client_id]

        while bucket and now - bucket[0] > WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT:
            retry_after = int(
                max(
                    1,
                    WINDOW_SECONDS - (now - bucket[0])
                )
            )

            return Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={
                    "Retry-After": str(retry_after)
                }
            )

        bucket.append(now)

    return await call_next(request)


@app.get("/")
def root():
    return {"status": "ok"}


# -------------------------
# Idempotent POST /orders
# -------------------------

@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key"
    )
):
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Missing Idempotency-Key"
        )

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4())
    }

    idempotency_store[idempotency_key] = order

    return order


# -------------------------
# Cursor pagination
# -------------------------

@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: Optional[str] = None
):
    start_index = 0

    if cursor:
        try:
            start_index = int(
                base64.b64decode(cursor.encode()).decode()
            )
        except Exception:
            start_index = 0

    end_index = min(
        start_index + limit,
        TOTAL_ORDERS
    )

    items = ORDERS[start_index:end_index]

    next_cursor = None

    if end_index < TOTAL_ORDERS:
        next_cursor = base64.b64encode(
            str(end_index).encode()
        ).decode()

    return {
        "items": items,
        "next_cursor": next_cursor
    }
