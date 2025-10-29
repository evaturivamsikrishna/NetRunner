# src/validators/failproof_validator.py
import re, time, sqlite3, json
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

DEFAULT_RENDERTRON = "https://render-tron.appspot.com/render/"
HEADERS_BASE = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
]

# Simple sqlite cache for recent results (2 day TTL)
class Cache:
    def __init__(self, path=".validator_cache.sqlite"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, value TEXT, ts REAL)")
    def get(self, key, ttl=172800):
        r = self.conn.execute("SELECT value,ts FROM cache WHERE key=?", (key,)).fetchone()
        if not r: return None
        val, ts = r
        if time.time() - ts > ttl:
            return None
        return json.loads(val)
    def set(self, key, value):
        now = time.time()
        self.conn.execute("REPLACE INTO cache(key,value,ts) VALUES(?,?,?)", (key, json.dumps(value), now))
        self.conn.commit()

cache = Cache()

# heuristics for soft 404 / error page
ERROR_PATTERNS = [
    r"page not found", r"404", r"not found", r"error", r"oops", r"nicht gefunden", r"no encontrado"
]

def looks_like_error(html_text):
    t = (html_text or "").lower()
    if len(t.strip()) < 500:
        return True
    for p in ERROR_PATTERNS:
        if p in t:
            return True
    return False

def fetch_rendertron(url, rendertron=DEFAULT_RENDERTRON, timeout=15):
    try:
        r = requests.get(rendertron, params={"url": url}, timeout=timeout)
        if r.status_code == 200:
            return r.text
    except Exception:
        return None
    return None

def normalize_url(url):
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if not urlparse(url).scheme:
        url = "https://" + url
    return url.rstrip("/")

def check_link_strict(url, rendertron=None, enable_js_fallback=False, session=None, timeout=8):
    """
    Returns dict:
    { url, status_code, status, reason, final_url, snippet, method }
    status in: OK, BROKEN, SOFT_404, IGNORED_403, TIMEOUT
    """
    url = normalize_url(url)
    cached = cache.get(url)
    if cached:
        return cached

    if session is None:
        session = requests.Session()

    headers = HEADERS_BASE.copy()
    headers["User-Agent"] = USER_AGENTS[0]

    # Try HEAD first (fast). Many servers block HEAD; if so fallback to GET.
    try:
        r = session.head(url, headers=headers, allow_redirects=True, timeout=5)
        code = r.status_code
    except requests.exceptions.RequestException:
        r = None
        code = None

    # If HEAD gave a server error or not supported -> fallback to GET
    if code is None or code >= 400 or code == 405:
        try:
            # rotate UA, add referer to reduce 403
            headers["User-Agent"] = USER_AGENTS[1]
            headers["Referer"] = "https://www.google.com/"
            r = session.get(url, headers=headers, allow_redirects=True, timeout=timeout)
            code = r.status_code
        except requests.exceptions.Timeout:
            result = {"url": url, "status_code": None, "status": "TIMEOUT", "reason": "timeout", "final_url": None}
            cache.set(url, result); return result
        except requests.exceptions.RequestException as e:
            result = {"url": url, "status_code": None, "status": "BROKEN", "reason": str(e), "final_url": None}
            cache.set(url, result); return result

    final_url = r.url if r is not None else url

    # Strict rules: treat 404,410,5xx as BROKEN
    if code in (404, 410) or (code and 500 <= code < 600):
        result = {"url": url, "status_code": code, "status": "BROKEN", "reason": f"HTTP {code}", "final_url": final_url}
        cache.set(url, result); return result

    # Ignore 403 as broken — mark IGNORED_403 (but optionally fallback)
    if code == 403:
        # Do one retry with different UA and referer — if still 403 then mark IGNORED_403
        try:
            headers["User-Agent"] = USER_AGENTS[2]
            headers["Referer"] = "https://www.bing.com/"
            rr = session.get(url, headers=headers, allow_redirects=True, timeout=6)
            if rr.status_code == 403:
                result = {"url": url, "status_code": 403, "status": "IGNORED_403", "reason": "403 - likely bot protection", "final_url": rr.url}
                cache.set(url, result); return result
            else:
                r = rr; code = rr.status_code; final_url = rr.url
        except Exception:
            result = {"url": url, "status_code": 403, "status": "IGNORED_403", "reason": "403 and retry failed", "final_url": final_url}
            cache.set(url, result); return result

    # If we got a 200-ish response, inspect body
    text = ""
    try:
        text = r.text or ""
    except Exception:
        text = ""

    # Soft 404 detection
    if looks_like_error(text):
        # try one fallback: use Rendertron (remote renderer) if enabled
        if enable_js_fallback and rendertron:
            rendered = fetch_rendertron(final_url, rendertron=rendertron, timeout=12)
            if rendered and not looks_like_error(rendered):
                result = {"url": url, "status_code": code, "status": "OK_RENDERED", "reason": "rendertron_success", "final_url": final_url, "snippet": (rendered[:400] if rendered else "")}
                cache.set(url, result); return result
            else:
                result = {"url": url, "status_code": code, "status": "SOFT_404", "reason": "soft_404_detected", "final_url": final_url, "snippet": text[:400]}
                cache.set(url, result); return result
        else:
            result = {"url": url, "status_code": code, "status": "SOFT_404", "reason": "soft_404_detected", "final_url": final_url, "snippet": text[:400]}
            cache.set(url, result); return result

    # If reached here, treat as OK
    result = {"url": url, "status_code": code, "status": "OK", "reason": f"HTTP {code}", "final_url": final_url}
    cache.set(url, result)
    return result