"""
DND Bridge - self-hosted AI API key bridge/proxy.

Users connect their own OpenAI-compatible AI provider API keys.
The app issues `dnd-...` keys bound to one provider (or a worker).
Clients use base URL https://<host>/v1 + the dnd- key like a normal
OpenAI endpoint. Usage (requests + tokens) is logged per key.
"""
import asyncio
import hashlib
import logging
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (FileResponse, JSONResponse, PlainTextResponse,
                               StreamingResponse)
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

# ---------------------------------------------------------------- config ---
JWT_SECRET = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    JWT_SECRET = "dev-secret-change-me"
    logging.warning("JWT_SECRET not set, using insecure dev fallback. "
                    "Set JWT_SECRET env var in production.")
JWT_ALG = "HS256"
JWT_EXPIRE_DAYS = 7

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "dnd_bridge.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")

RATE_LIMIT_PER_MIN = 60          # per dnd- key on /v1/*
WORKER_TIMEOUT_S = 55            # max wait for worker answer
WORKER_ONLINE_MIN = 10           # last_seen within N min = online

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ------------------------------------------------------------------ db ----
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        base_url TEXT NOT NULL,
        api_key TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        key_hash TEXT UNIQUE NOT NULL,
        key_prefix TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'provider',
        provider_id INTEGER,
        created_at TEXT NOT NULL,
        last_used_at TEXT,
        is_active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS workers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        token_hash TEXT UNIQUE NOT NULL,
        token_prefix TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_seen_at TEXT
    );
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        key_id INTEGER NOT NULL,
        model TEXT NOT NULL,
        messages TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        claimed_at TEXT,
        answered_at TEXT,
        answer_text TEXT
    );
    CREATE TABLE IF NOT EXISTS usage_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        ts TEXT NOT NULL,
        model TEXT NOT NULL DEFAULT '',
        prompt_tokens INTEGER NOT NULL DEFAULT 0,
        completion_tokens INTEGER NOT NULL DEFAULT 0,
        status INTEGER NOT NULL DEFAULT 200,
        latency_ms INTEGER NOT NULL DEFAULT 0,
        endpoint TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_keys_hash ON keys(key_hash);
    CREATE INDEX IF NOT EXISTS idx_usage_key_ts ON usage_log(key_id, ts);
    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, user_id);
    """)
    con.commit()
    con.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def mask_secret(s: str) -> str:
    if not s:
        return "-"
    return "\u2022\u2022\u2022\u2022" + s[-4:]


# ---------------------------------------------------------------- auth ----
def create_token(user_id: int, username: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "username": username, "exp": exp},
                      JWT_SECRET, algorithm=JWT_ALG)


def get_current_user(authorization: str = Header("")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization: Bearer token")
    token = authorization[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid or expired token")
    con = db()
    row = con.execute("SELECT id, username, created_at FROM users WHERE id=?",
                      (uid,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(401, "User not found")
    return dict(row)


def get_worker(authorization: str = Header("")) -> dict:
    """Auth for worker agents via their worker token."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization: Bearer token")
    th = sha256(authorization[7:])
    con = db()
    row = con.execute("SELECT * FROM workers WHERE token_hash=?",
                      (th,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(401, "Invalid worker token")
    return dict(row)


# ------------------------------------------------------- rate limit ----
_rate_buckets: dict = {}


def check_rate_limit(key_hash: str):
    now = time.time()
    bucket = _rate_buckets.get(key_hash, [])
    bucket = [t for t in bucket if now - t < 60]
    if len(bucket) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(429, "Rate limit exceeded: 60 req/min per key")
    bucket.append(now)
    _rate_buckets[key_hash] = bucket


# ---------------------------------------------------------------- models --
class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    username: str
    password: str


class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=8, max_length=256)
    api_key: str = Field(min_length=4, max_length=512)


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    mode: str = "provider"
    provider_id: int | None = None


class WorkerIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class AnswerIn(BaseModel):
    text: str = Field(min_length=1)


# ------------------------------------------------------------------ app ---
app = FastAPI(title="DND Bridge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()
    logging.getLogger("uvicorn").info("DND Bridge ready, db=%s", DB_PATH)


@app.get("/api/health")
def health():
    return {"ok": True}


# ----------------------------------------------------------------- auth ---
@app.post("/api/auth/register")
def register(body: RegisterIn):
    username = body.username.strip()
    if len(username) < 3:
        raise HTTPException(400, "Username minimal 3 karakter")
    con = db()
    exists = con.execute("SELECT id FROM users WHERE username=?",
                         (username,)).fetchone()
    if exists:
        con.close()
        raise HTTPException(400, "Username sudah dipakai")
    cur = con.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
        (username, pwd_ctx.hash(body.password), now_iso()))
    uid = cur.lastrowid
    con.commit()
    con.close()
    return {"token": create_token(uid, username), "username": username}


@app.post("/api/auth/login")
def login(body: LoginIn):
    con = db()
    row = con.execute("SELECT * FROM users WHERE username=?",
                      (body.username.strip(),)).fetchone()
    con.close()
    if not row or not pwd_ctx.verify(body.password, row["password_hash"]):
        raise HTTPException(401, "Username atau password salah")
    return {"token": create_token(row["id"], row["username"]),
            "username": row["username"]}


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"],
            "created_at": user["created_at"]}

# ------------------------------------------------------------- providers --
async def validate_provider(base_url: str, api_key: str) -> tuple[bool, str]:
    """Call GET {base_url}/models to validate the provider credentials."""
    url = base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.TimeoutException:
        return False, "Timeout: provider tidak merespons dalam 5 detik"
    except httpx.ConnectError:
        return False, "Tidak bisa terhubung ke base_url provider"
    except Exception as e:
        return False, f"Error koneksi: {e}"
    if r.status_code == 401:
        return False, "API key ditolak provider (401 Unauthorized)"
    if r.status_code >= 400:
        return False, f"Provider mengembalikan HTTP {r.status_code}"
    return True, "ok"


@app.post("/api/providers")
async def add_provider(body: ProviderIn, user: dict = Depends(get_current_user)):
    base_url = body.base_url.strip().rstrip("/")
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise HTTPException(400, "base_url harus diawali http:// atau https://")
    ok, msg = await validate_provider(base_url, body.api_key.strip())
    if not ok:
        raise HTTPException(400, f"Validasi provider gagal: {msg}")
    con = db()
    cur = con.execute(
        "INSERT INTO providers (user_id, name, base_url, api_key, created_at)"
        " VALUES (?,?,?,?,?)",
        (user["id"], body.name.strip(), base_url, body.api_key.strip(), now_iso()))
    pid = cur.lastrowid
    con.commit()
    con.close()
    return {"id": pid, "name": body.name.strip(), "base_url": base_url}


@app.get("/api/providers")
def list_providers(user: dict = Depends(get_current_user)):
    con = db()
    rows = con.execute(
        "SELECT id, name, base_url, api_key, created_at FROM providers"
        " WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    con.close()
    return [{"id": r["id"], "name": r["name"], "base_url": r["base_url"],
             "api_key_masked": mask_secret(r["api_key"]),
             "created_at": r["created_at"]} for r in rows]


@app.delete("/api/providers/{pid}")
def delete_provider(pid: int, user: dict = Depends(get_current_user)):
    con = db()
    row = con.execute("SELECT id FROM providers WHERE id=? AND user_id=?",
                      (pid, user["id"])).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "Provider tidak ditemukan")
    # keys bound to this provider keep working? No - block delete if keys use it.
    n = con.execute("SELECT COUNT(*) c FROM keys WHERE provider_id=?",
                    (pid,)).fetchone()["c"]
    if n:
        con.close()
        raise HTTPException(400,
                            f"Tidak bisa dihapus: {n} key masih memakai provider ini")
    con.execute("DELETE FROM providers WHERE id=?", (pid,))
    con.commit()
    con.close()
    return {"ok": True}


# ------------------------------------------------------------------ keys --
def make_dnd_key() -> str:
    return "dnd-" + secrets.token_urlsafe(32)


@app.post("/api/keys")
def create_key(body: KeyIn, user: dict = Depends(get_current_user)):
    mode = body.mode.strip().lower()
    if mode not in ("provider", "worker"):
        raise HTTPException(400, "mode harus 'provider' atau 'worker'")
    provider_id = None
    if mode == "provider":
        if not body.provider_id:
            raise HTTPException(400, "provider_id wajib untuk mode provider")
        con = db()
        prow = con.execute("SELECT id FROM providers WHERE id=? AND user_id=?",
                           (body.provider_id, user["id"])).fetchone()
        con.close()
        if not prow:
            raise HTTPException(400, "Provider tidak ditemukan")
        provider_id = body.provider_id
    full_key = make_dnd_key()
    con = db()
    cur = con.execute(
        "INSERT INTO keys (user_id, name, key_hash, key_prefix, mode,"
        " provider_id, created_at, is_active)"
        " VALUES (?,?,?,?,?,?,?,1)",
        (user["id"], body.name.strip(), sha256(full_key), full_key[:12],
         mode, provider_id, now_iso()))
    kid = cur.lastrowid
    con.commit()
    con.close()
    # full key is shown ONLY here, never again
    return {"id": kid, "name": body.name.strip(), "mode": mode,
            "key": full_key, "key_prefix": full_key[:12]}


@app.get("/api/keys")
def list_keys(user: dict = Depends(get_current_user)):
    con = db()
    rows = con.execute(
        """SELECT k.id, k.name, k.key_prefix, k.mode, k.provider_id, k.created_at,
                  k.last_used_at, k.is_active, p.name AS provider_name,
                  (SELECT COUNT(*) FROM usage_log u WHERE u.key_id=k.id) AS reqs,
                  (SELECT COALESCE(SUM(u.prompt_tokens),0) FROM usage_log u WHERE u.key_id=k.id) AS ptok,
                  (SELECT COALESCE(SUM(u.completion_tokens),0) FROM usage_log u WHERE u.key_id=k.id) AS ctok
           FROM keys k LEFT JOIN providers p ON p.id=k.provider_id
           WHERE k.user_id=? ORDER BY k.id DESC""", (user["id"],)).fetchall()
    wrows = con.execute(
        "SELECT name, last_seen_at FROM workers WHERE user_id=? ORDER BY last_seen_at DESC",
        (user["id"],)).fetchall()
    con.close()
    winfo = None
    if wrows:
        winfo = {"name": wrows[0]["name"],
                 "is_online": any(worker_online(w["last_seen_at"]) for w in wrows),
                 "count": len(wrows)}
    return [{"id": r["id"], "name": r["name"],
             "key_display": r["key_prefix"] + "\u2022\u2022\u2022\u2022",
             "mode": r["mode"], "provider_id": r["provider_id"],
             "provider_name": r["provider_name"],
             "created_at": r["created_at"], "last_used_at": r["last_used_at"],
             "is_active": bool(r["is_active"]),
             "total_requests": r["reqs"],
             "prompt_tokens": r["ptok"], "completion_tokens": r["ctok"],
             "total_tokens": r["ptok"] + r["ctok"],
             "worker": winfo}
            for r in rows]


@app.delete("/api/keys/{kid}")
def delete_key(kid: int, user: dict = Depends(get_current_user)):
    con = db()
    row = con.execute("SELECT id FROM keys WHERE id=? AND user_id=?",
                      (kid, user["id"])).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "Key tidak ditemukan")
    con.execute("DELETE FROM keys WHERE id=?", (kid,))
    con.commit()
    con.close()
    return {"ok": True}


@app.post("/api/keys/{kid}/toggle")
def toggle_key(kid: int, user: dict = Depends(get_current_user)):
    con = db()
    row = con.execute("SELECT is_active FROM keys WHERE id=? AND user_id=?",
                      (kid, user["id"])).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "Key tidak ditemukan")
    new = 0 if row["is_active"] else 1
    con.execute("UPDATE keys SET is_active=? WHERE id=?", (new, kid))
    con.commit()
    con.close()
    return {"ok": True, "is_active": bool(new)}


# ---------------------------------------------------------------- workers --
@app.post("/api/workers")
def create_worker(body: WorkerIn, user: dict = Depends(get_current_user)):
    token = "dndw-" + secrets.token_urlsafe(32)
    con = db()
    cur = con.execute(
        "INSERT INTO workers (user_id, name, token_hash, token_prefix,"
        " created_at) VALUES (?,?,?,?,?)",
        (user["id"], body.name.strip(), sha256(token), token[:12], now_iso()))
    wid = cur.lastrowid
    con.commit()
    con.close()
    return {"id": wid, "name": body.name.strip(), "token": token,
            "token_prefix": token[:12]}


def worker_online(last_seen: str | None) -> bool:
    if not last_seen:
        return False
    try:
        dt = datetime.fromisoformat(last_seen)
        return (datetime.now(timezone.utc) - dt).total_seconds() < WORKER_ONLINE_MIN * 60
    except Exception:
        return False


@app.get("/api/workers")
def list_workers(user: dict = Depends(get_current_user)):
    con = db()
    rows = con.execute(
        "SELECT id, name, token_prefix, created_at, last_seen_at FROM workers"
        " WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    con.close()
    return [{"id": r["id"], "name": r["name"],
             "token_display": r["token_prefix"] + "\u2022\u2022\u2022\u2022",
             "created_at": r["created_at"], "last_seen_at": r["last_seen_at"],
             "is_online": worker_online(r["last_seen_at"])} for r in rows]


@app.delete("/api/workers/{wid}")
def delete_worker(wid: int, user: dict = Depends(get_current_user)):
    con = db()
    row = con.execute("SELECT id FROM workers WHERE id=? AND user_id=?",
                      (wid, user["id"])).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "Worker tidak ditemukan")
    con.execute("DELETE FROM workers WHERE id=?", (wid,))
    con.commit()
    con.close()
    return {"ok": True}


# ------------------------------------------------- worker agent endpoints --
@app.post("/api/worker/ping")
def worker_ping(worker: dict = Depends(get_worker)):
    con = db()
    con.execute("UPDATE workers SET last_seen_at=? WHERE id=?",
                (now_iso(), worker["id"]))
    n = con.execute(
        "SELECT COUNT(*) c FROM jobs WHERE user_id=? AND status='pending'",
        (worker["user_id"],)).fetchone()["c"]
    con.commit()
    con.close()
    return {"ok": True, "pending_jobs": n}


@app.get("/api/worker/jobs/next")
def worker_next_job(worker: dict = Depends(get_worker)):
    con = db()
    row = con.execute(
        "SELECT id, key_id, model, messages, created_at FROM jobs"
        " WHERE user_id=? AND status='pending' ORDER BY id ASC LIMIT 1",
        (worker["user_id"],)).fetchone()
    if not row:
        con.close()
        return Response(status_code=204)
    con.execute("UPDATE jobs SET status='claimed', claimed_at=? WHERE id=?",
                (now_iso(), row["id"]))
    con.commit()
    con.close()
    import json
    return {"id": row["id"], "key_id": row["key_id"], "model": row["model"],
            "messages": json.loads(row["messages"]),
            "created_at": row["created_at"]}


@app.post("/api/worker/jobs/{jid}/answer")
def worker_answer(jid: int, body: AnswerIn, worker: dict = Depends(get_worker)):
    con = db()
    row = con.execute("SELECT id, status FROM jobs WHERE id=? AND user_id=?",
                      (jid, worker["user_id"])).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "Job tidak ditemukan")
    if row["status"] == "done":
        con.close()
        raise HTTPException(400, "Job sudah dijawab")
    con.execute("UPDATE jobs SET status='done', answered_at=?, answer_text=?"
                " WHERE id=?", (now_iso(), body.text, jid))
    con.commit()
    con.close()
    return {"ok": True}

# ----------------------------------------------------------------- usage --
@app.get("/api/usage/summary")
def usage_summary(user: dict = Depends(get_current_user)):
    con = db()
    per_key = con.execute(
        """SELECT k.id, k.name, k.key_prefix,
                  COUNT(u.id) AS requests,
                  COALESCE(SUM(u.prompt_tokens),0) AS prompt_tokens,
                  COALESCE(SUM(u.completion_tokens),0) AS completion_tokens
           FROM keys k LEFT JOIN usage_log u ON u.key_id=k.id
           WHERE k.user_id=? GROUP BY k.id ORDER BY requests DESC""",
        (user["id"],)).fetchall()
    days = []
    for i in range(13, -1, -1):
        d = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
        row = con.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(prompt_tokens+completion_tokens),0) t"
            " FROM usage_log WHERE user_id=? AND substr(ts,1,10)=?",
            (user["id"], d)).fetchone()
        days.append({"date": d, "requests": row["c"], "tokens": row["t"]})
    con.close()
    return {"per_key": [dict(r) for r in per_key], "per_day": days}


# ------------------------------------------------------------------ proxy --
def _bearer_key(authorization: str = Header("")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization: Bearer dnd-... key")
    return authorization[7:]


def resolve_dnd_key(raw: str) -> dict:
    kh = sha256(raw)
    check_rate_limit(kh)
    con = db()
    row = con.execute("SELECT * FROM keys WHERE key_hash=?", (kh,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(401, "Invalid API key")
    key = dict(row)
    if not key["is_active"]:
        raise HTTPException(401, "API key dinonaktifkan")
    con = db()
    con.execute("UPDATE keys SET last_used_at=? WHERE id=?",
                (now_iso(), key["id"]))
    con.commit()
    con.close()
    return key


def get_provider_for_key(key: dict) -> dict:
    con = db()
    row = con.execute("SELECT * FROM providers WHERE id=?",
                      (key["provider_id"],)).fetchone()
    con.close()
    if not row:
        raise HTTPException(502, "Provider untuk key ini tidak ditemukan")
    return dict(row)


def log_usage(key: dict, model: str, pt: int, ct: int, status: int,
              latency_ms: int, endpoint: str):
    con = db()
    con.execute(
        "INSERT INTO usage_log (key_id, user_id, ts, model, prompt_tokens,"
        " completion_tokens, status, latency_ms, endpoint)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (key["id"], key["user_id"], now_iso(), model or "", pt, ct,
         status, latency_ms, endpoint))
    con.commit()
    con.close()


@app.get("/v1/models")
async def v1_models(authorization: str = Header("")):
    raw = _bearer_key(authorization)
    key = resolve_dnd_key(raw)
    t0 = time.time()
    if key["mode"] == "worker":
        log_usage(key, "dnd-worker", 0, 0, 200,
                  int((time.time() - t0) * 1000), "/v1/models")
        return {"object": "list", "data": [
            {"id": "dnd-worker", "object": "model",
             "created": int(time.time()), "owned_by": "dnd-bridge"}]}
    prov = get_provider_for_key(key)
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
            r = await client.get(prov["base_url"].rstrip("/") + "/models",
                                 headers={"Authorization": f"Bearer {prov['api_key']}"})
        log_usage(key, "", 0, 0, r.status_code,
                  int((time.time() - t0) * 1000), "/v1/models")
        return JSONResponse(status_code=r.status_code, content=r.json())
    except Exception as e:
        log_usage(key, "", 0, 0, 502, int((time.time() - t0) * 1000),
                  "/v1/models")
        raise HTTPException(502, f"Provider error: {e}")


def _provider_headers(prov: dict, extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {prov['api_key']}",
         "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


async def _proxy_chat(provider: dict, body: dict, key: dict, endpoint: str):
    """Forward chat/completions to provider. Handles stream + non-stream."""
    t0 = time.time()
    model = body.get("model", "")
    stream = bool(body.get("stream"))
    url = provider["base_url"].rstrip("/") + "/chat/completions"
    if stream:
        async def gen():
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=120) as client:
                    async with client.stream("POST", url,
                                             headers=_provider_headers(provider),
                                             json=body) as r:
                        async for chunk in r.aiter_bytes():
                            yield chunk
            except Exception as e:
                yield f'data: {{"error": "proxy stream error: {e}"}}\n\n'.encode()
        # streaming: token count unknown -> log request only
        log_usage(key, model, 0, 0, 200, int((time.time() - t0) * 1000),
                  endpoint + "?stream")
        return StreamingResponse(gen(), media_type="text/event-stream")
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=120) as client:
            r = await client.post(url, headers=_provider_headers(provider),
                                  json=body)
    except Exception as e:
        log_usage(key, model, 0, 0, 502, int((time.time() - t0) * 1000),
                  endpoint)
        raise HTTPException(502, f"Provider error: {e}")
    try:
        data = r.json()
    except Exception:
        log_usage(key, model, 0, 0, r.status_code,
                  int((time.time() - t0) * 1000), endpoint)
        return Response(content=r.content, status_code=r.status_code,
                        media_type=r.headers.get("content-type",
                                                 "application/json"))
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    pt = int(usage.get("prompt_tokens", 0) or 0)
    ct = int(usage.get("completion_tokens", 0) or 0)
    log_usage(key, model, pt, ct, r.status_code,
              int((time.time() - t0) * 1000), endpoint)
    return JSONResponse(status_code=r.status_code, content=data)


async def _worker_chat(key: dict, body: dict, endpoint: str):
    """Worker mode: queue a job and wait up to WORKER_TIMEOUT_S for an answer."""
    import json as _json
    t0 = time.time()
    model = body.get("model", "dnd-worker")
    messages = body.get("messages", [])
    con = db()
    cur = con.execute(
        "INSERT INTO jobs (user_id, key_id, model, messages, status, created_at)"
        " VALUES (?,?,?,?, 'pending', ?)",
        (key["user_id"], key["id"], model, _json.dumps(messages), now_iso()))
    jid = cur.lastrowid
    con.commit()
    answer = None
    deadline = time.time() + WORKER_TIMEOUT_S
    while time.time() < deadline:
        await asyncio.sleep(1)
        row = con.execute("SELECT status, answer_text FROM jobs WHERE id=?",
                          (jid,)).fetchone()
        if row and row["status"] == "done":
            answer = row["answer_text"]
            break
    con.close()
    latency = int((time.time() - t0) * 1000)
    if answer is None:
        log_usage(key, model, 0, 0, 504, latency, endpoint + "+worker")
        raise HTTPException(504, "Tidak ada worker yang menjawab dalam"
                                f" {WORKER_TIMEOUT_S} detik")
    log_usage(key, model, 0, 0, 200, latency, endpoint + "+worker")
    return {
        "id": f"chatcmpl-dnd{jid}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": answer},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                  "total_tokens": 0},
    }


@app.post("/v1/chat/completions")
async def v1_chat_completions(request: Request,
                              authorization: str = Header("")):
    raw = _bearer_key(authorization)
    key = resolve_dnd_key(raw)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Body harus JSON valid")
    if key["mode"] == "worker":
        return await _worker_chat(key, body, "/v1/chat/completions")
    prov = get_provider_for_key(key)
    return await _proxy_chat(prov, body, key, "/v1/chat/completions")


@app.post("/v1/completions")
async def v1_completions(request: Request, authorization: str = Header("")):
    raw = _bearer_key(authorization)
    key = resolve_dnd_key(raw)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Body harus JSON valid")
    t0 = time.time()
    model = body.get("model", "")
    if key["mode"] == "worker":
        raise HTTPException(400, "Worker mode hanya mendukung /v1/chat/completions")
    prov = get_provider_for_key(key)
    url = prov["base_url"].rstrip("/") + "/completions"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=120) as client:
            r = await client.post(url, headers=_provider_headers(prov), json=body)
        data = r.json()
    except Exception as e:
        log_usage(key, model, 0, 0, 502, int((time.time() - t0) * 1000),
                  "/v1/completions")
        raise HTTPException(502, f"Provider error: {e}")
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    log_usage(key, model, int(usage.get("prompt_tokens", 0) or 0),
              int(usage.get("completion_tokens", 0) or 0), r.status_code,
              int((time.time() - t0) * 1000), "/v1/completions")
    return JSONResponse(status_code=r.status_code, content=data)


# ------------------------------------------------------- static pages ----
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=FileResponse)
def landing():
    p = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(p):
        return FileResponse(p)
    return PlainTextResponse("DND Bridge API - lihat /api/health")


@app.get("/app", response_class=FileResponse)
def dashboard():
    p = os.path.join(STATIC_DIR, "app.html")
    if os.path.exists(p):
        return FileResponse(p)
    return PlainTextResponse("Dashboard belum tersedia")
