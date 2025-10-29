# src/validators/advanced_link_checker.py
# Drop-in async validator with:
# - UA rotation, Referer header
# - HEAD -> GET fallback
# - canonical resolution
# - localized fallback (/de-de -> /)
# - soft-404 detection (visible text/title)
# - optional Playwright JS-render fallback (ENABLE_JS_RENDER flag)
# - returns dict: {url, final_url, status, status_code, reason, snippet, localized_rescue, canonical_match, js_recovery}
import re
import asyncio
from urllib.parse import urlparse, urljoin
from warnings import filterwarnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
]

ERROR_PATTERNS = [
    r"page not found",
    r"\b404\b",
    r"not found",
    r"something went wrong",
    r"an unexpected error",
    r"error loading",
    r"not available",
    r"nicht gefunden",
    r"se ha producido un error",
    r"oops",
]

LOCALE_RE = re.compile(r"/[a-z]{2}-[a-z]{2}/", re.I)

ENABLE_JS_RENDER = (
    False  # Set True to enable Playwright fallback (requires playwright installed)
)


async def _maybe_js_check(url, timeout=15):
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return False, None, "playwright-not-installed"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            text = await page.content()
            await browser.close()
            return True, text, None
    except Exception as e:
        return False, None, str(e)


def _choose_headers(extra=None):
    import random

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive",
    }
    if extra:
        headers.update(extra)
    return headers


def _is_soft_404_text(text):
    if not text:
        return False
    t = text.lower()
    for pat in ERROR_PATTERNS:
        if re.search(pat, t):
            return True
    # very short bodies often mean redirect/blank pages
    if len(t.strip()) < 300:
        return True
    return False


async def check_link_strict(
    url, session=None, async_resp=None, timeout=20, enable_js=ENABLE_JS_RENDER
):
    """
    Async-friendly strict link checker.
    - session: aiohttp.ClientSession (recommended)
    - async_resp: aiohttp response object already fetched (optional optimization)
    Returns a dict with keys described above.
    """
    result = {
        "url": url,
        "final_url": url,
        "status": "UNKNOWN",
        "status_code": None,
        "reason": "",
        "snippet": "",
        "localized_rescue": False,
        "canonical_match": False,
        "js_recovery": False,
    }

    headers = _choose_headers()

    # Helper to parse HTML and check canonical / errors
    async def _analyze_html(html, current_final):
        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.string if soup.title else "") or ""
        visible_text = " ".join(soup.stripped_strings)[:5000]
        snippet = (
            (visible_text[:400] + "...") if len(visible_text) > 400 else visible_text
        )
        # canonical
        can = None
        link_tag = soup.find("link", {"rel": "canonical"})
        if link_tag and link_tag.get("href"):
            can = urljoin(current_final, link_tag.get("href"))
        # error detection
        soft = _is_soft_404_text(title + " " + visible_text)
        return {
            "title": title,
            "visible_text": visible_text,
            "snippet": snippet,
            "canonical": can,
            "soft": soft,
        }

    # Async fetch helpers (aiohttp expected)
    async def _head_then_get(surl):
        try:
            if async_resp is not None:
                resp = async_resp
                status = getattr(resp, "status", None)
                final = getattr(resp, "url", surl)
                text = await resp.text() if status and status < 500 else ""
                return status, str(final), text
            # HEAD first
            try:
                async with session.head(
                    surl, headers=headers, allow_redirects=True, timeout=timeout
                ) as h:
                    status = h.status
                    final = str(h.url)
                    # some servers mis-handle HEAD: treat 405/501 as signal to GET
                    if status in (405, 501) or status >= 400:
                        # fallback to GET
                        raise RuntimeError("HEAD-fallback")
                    return status, final, ""
            except Exception:
                # GET fallback
                async with session.get(
                    surl, headers=headers, allow_redirects=True, timeout=timeout
                ) as g:
                    status = g.status
                    final = str(g.url)
                    # read body
                    text = await g.text(errors="ignore")
                    return status, final, text
        except Exception as e:
            return None, surl, f"__EXC__:{e}"

    # Primary check
    try:
        status, final_url, body = await _head_then_get(url)
        result["status_code"] = status or 0
        result["final_url"] = final_url
        if status is None:
            result["status"] = "N/A"
            result["reason"] = body or "no-response"
            return result

        # Strict broken rules: only mark broken for 404/410/5xx (per request), else do heuristics
        if status >= 500 or status == 404 or status == 410:
            result["status"] = "BROKEN"
            result["reason"] = f"HTTP {status}"
            # capture snippet if we have body
            if body:
                analysed = await _analyze_html(body, final_url)
                result["snippet"] = analysed["snippet"]
            return result

        # If 200-ish, analyze content for soft 404 or canonical
        analysed = {}
        if body:
            analysed = await _analyze_html(body, final_url)
        else:
            # no body available (HEAD returned) - try lightweight GET to inspect title/text
            try:
                async with session.get(
                    final_url,
                    headers=_choose_headers({"Referer": url}),
                    timeout=timeout,
                ) as g2:
                    txt = await g2.text(errors="ignore")
                    analysed = await _analyze_html(txt, final_url)
            except Exception:
                analysed = {
                    "title": "",
                    "visible_text": "",
                    "snippet": "",
                    "canonical": None,
                    "soft": False,
                }

        # canonical handling
        if analysed.get("canonical"):
            # normalize compare
            can = analysed["canonical"].rstrip("/") if analysed["canonical"] else None
            final_cmp = final_url.rstrip("/") if final_url else final_url
            if can and final_cmp and (can.rstrip("/") == final_cmp.rstrip("/")):
                result["canonical_match"] = True

        # soft-404 detection
        if analysed.get("soft"):
            # treat as SOFT_404 but not hard broken
            result["status"] = "SOFT_404"
            result["status_code"] = status
            result["reason"] = "Soft/visible error detected"
            result["snippet"] = analysed.get("snippet", "")
            return result

        # localized fallback: try removing locale path if present and validate quickly
        if LOCALE_RE.search(final_url):
            fallback = LOCALE_RE.sub("/", final_url, count=1)
            if fallback and fallback != final_url:
                try:
                    async with session.head(
                        fallback,
                        headers=_choose_headers({"Referer": final_url}),
                        allow_redirects=True,
                        timeout=8,
                    ) as fh:
                        if fh.status == 200:
                            result["localized_rescue"] = True
                            result["status"] = "OK"
                            result["reason"] = "Localized fallback succeeded"
                            result["final_url"] = str(fh.url)
                            return result
                except Exception:
                    # try GET
                    try:
                        async with session.get(
                            fallback,
                            headers=_choose_headers({"Referer": final_url}),
                            allow_redirects=True,
                            timeout=8,
                        ) as fg:
                            if fg.status == 200:
                                result["localized_rescue"] = True
                                result["status"] = "OK"
                                result["reason"] = "Localized fallback succeeded"
                                result["final_url"] = str(fg.url)
                                return result
                    except Exception:
                        pass

        # Cloudflare / bot blocking heuristics (403 but valid content)
        if status == 403:
            # if body contains typical cf challenge text, consider soft
            if body and "cloudflare" in body.lower():
                result["status"] = "SOFT_403"
                result["status_code"] = 403
                result["reason"] = "Cloudflare / Bot protection detected (soft)"
                result["snippet"] = analysed.get("snippet", "")
                # optional JS render attempt if allowed
                if enable_js:
                    ok, js_text, js_err = await _maybe_js_check(final_url)
                    if ok and js_text and not _is_soft_404_text(js_text):
                        result["js_recovery"] = True
                        result["status"] = "OK"
                        result["status_code"] = 200
                        result["reason"] = "Recovered via JS render"
                        result["snippet"] = (
                            (js_text[:400] + "...") if len(js_text) > 400 else js_text
                        )
                return result
            else:
                # treat as not broken by strict rules (per request)
                result["status"] = "OK"
                result["status_code"] = 403
                result["reason"] = "403 treated as OK (soft)"
                return result

        # If reached here, normal OK page
        result["status"] = "OK"
        result["status_code"] = status
        result["reason"] = f"HTTP {status}"
        result["snippet"] = analysed.get("snippet", "") if analysed else ""
        return result

    except Exception as e:
        # last-resort JS fallback if enabled
        if enable_js:
            ok, js_text, js_err = await _maybe_js_check(url)
            if ok and js_text and not _is_soft_404_text(js_text):
                return {
                    "url": url,
                    "final_url": url,
                    "status": "OK",
                    "status_code": 200,
                    "reason": "Recovered via JS render (exception path)",
                    "snippet": (
                        (js_text[:400] + "...") if len(js_text) > 400 else js_text
                    ),
                    "js_recovery": True,
                }
        return {
            "url": url,
            "final_url": url,
            "status": "N/A",
            "status_code": 0,
            "reason": str(e),
        }


# -----------------------------------------------------------
# Compatibility alias for older imports
# -----------------------------------------------------------
check_link_advanced = check_link_strict

if __name__ == "__main__":
    import aiohttp, asyncio

    async def _test():
        async with aiohttp.ClientSession() as s:
            url = "https://example.com"
            result = await check_link_strict(url, session=s)
            print(result)

    asyncio.run(_test())
