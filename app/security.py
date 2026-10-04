"""Modul keamanan: CSRF, rate limit, TOTP (2FA), filter konten, header keamanan."""
import base64, hashlib, hmac, re, secrets, struct, time
from collections import defaultdict, deque
from functools import wraps
from flask import request, session, abort, jsonify

# ---------- CSRF ----------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf():
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    if not sent or not hmac.compare_digest(sent, session.get("_csrf", "")):
        abort(400, "Token keamanan tidak valid. Muat ulang halaman lalu coba lagi.")


# ---------- Rate limit (in-memory, per proses) ----------
_hits = defaultdict(deque)


def client_ip():
    return request.remote_addr or "0.0.0.0"


def rate_limit(name, limit, window):
    def deco(fn):
        @wraps(fn)
        def wrap(*a, **kw):
            if request.method != "POST":
                return fn(*a, **kw)
            key = (name, client_ip())
            now = time.time()
            q = _hits[key]
            while q and q[0] < now - window:
                q.popleft()
            if len(q) >= limit:
                if request.is_json or request.path.startswith("/api/"):
                    return jsonify(error="Terlalu banyak permintaan. Coba lagi beberapa saat."), 429
                abort(429)
            q.append(now)
            return fn(*a, **kw)
        return wrap
    return deco


# ---------- TOTP (RFC 6238) ----------
def new_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _hotp(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = digest[-1] & 15
    return (struct.unpack(">I", digest[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000


def verify_totp(secret, code, window=1):
    code = re.sub(r"\D", "", code or "")
    if len(code) != 6:
        return False
    step = int(time.time() // 30)
    return any(hmac.compare_digest(f"{_hotp(secret, step + d):06d}", code) for d in range(-window, window + 1))


def totp_uri(secret, user):
    return f"otpauth://totp/Portal%20Muara%20Enim:{user}?secret={secret}&issuer=Portal%20Muara%20Enim"


# ---------- Penyaringan konten negatif ----------
BLOCKED = [
    r"\bjudi\s*(online|bola)?\b", r"\bslot\s*(gacor|online|maxwin)\b", r"\btogel\b", r"\bsitus\s*judi\b",
    r"\bpinjol\s*ilegal\b", r"\bporno\w*\b", r"\bbokep\b", r"\bxxx\b", r"\bsex\s*(video|chat)\b",
    r"\bjual\s*(narkoba|sabu|ganja)\b", r"\bbunuh\s+(saja|dia|mereka)\b",
    r"https?://\S*(bit\.ly|tinyurl|t\.me)\S*",
]
_BLOCK_RE = [re.compile(p, re.I) for p in BLOCKED]


def is_negative_content(*texts):
    blob = " ".join(t or "" for t in texts)
    return any(r.search(blob) for r in _BLOCK_RE)


def clean(s, maxlen=2000):
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", (s or "").strip())
    return s[:maxlen]


# ---------- Header keamanan ----------
def apply_headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.path.startswith(("/admin", "/lacak", "/pengaduan", "/layanan", "/api")):
        resp.headers["Cache-Control"] = "no-store"
    return resp
