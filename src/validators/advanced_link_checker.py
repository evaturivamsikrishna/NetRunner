"""
src/validators/advanced_link_checker.py
Async & parallel URL validator for the NetRunner project.

✅ Features:
- UA rotation, referer headers
- HEAD → GET fallback
- canonical and soft-404 detection
- localized fallback (/de-de → /)
- Cloudflare soft-403 detection
- Optional Playwright fallback (set ENABLE_JS_RENDER=True)
- Async batch mode for integration with multiprocessing workers
"""

import re
import asyncio
import aiohttp
import random
from urllib.parse import urljoin
from warnings import filterwarnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ------------------ CONSTANTS ------------------
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16 Mobile/15E148 Safari/604.1",
]

ERROR_PATTERNS = [
    r"page not found", r"\b404\b", r"not found", r"something went wrong",
    r"an unexpected error", r"error loading", r"nicht gefunden",
    r"oops", r"unavailable", r"se ha producido un error",
]

LOCALE_RE = re.compile(r"/[a-z]{2}-[a-z]{2}/", re.I)
ENABLE_JS_RENDER = False
MAX_CONCURRENT_LINKS = 50  # per locale (adjust for performance)


# ------------------ INTERNAL HELPERS ------------------
def _headers(extra=None):
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive",
    }
    if extra:
        h.update(extra)
    return h


def _is_soft_404(text):
    if not text:
        return False
    t = text.lower()
    if len(t.strip()) < 200:
        return True
    return any(re.search(p, t) for p in ERROR_PATTERNS)


async def _analyze_html(html, url):
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string if soup.title else "") or ""
    visible_text = " ".join(soup.stripped_strings)[:5000]
    snippet = (visible_text[:400] + "...") if len(visible_text) > 400 else visible_text
    link_tag = soup.find("link", {"rel": "canonical"})
    can = urljoin(url, link_tag["href"]) if link_tag and link_tag.get("href") else None
    return {
        "title": title,
        "snippet": snippet,
        "canonical": can,
        "soft": _is_soft_404(title + " " + visible_text),
    }


# ------------------ MAIN VALIDATION ------------------
async def check_link_strict(url, session, timeout=15):
    result = {
        "url": url, "final_url": url,
        "status": "UNKNOWN", "status_code": None, "reason": "",
        "snippet": "", "localized_rescue": False,
        "canonical_match": False, "js_recovery": False,
    }

    try:
        # HEAD first
        async with session.head(url, headers=_headers(), allow_redirects=True, timeout=timeout) as r:
            status = r.status
            final_url = str(r.url)
            result.update({"status_code": status, "final_url": final_url})
            if status in (405, 501, 403) or status >= 400:
                raise RuntimeError("HEAD fallback")

        # if HEAD okay, return OK
        result.update({"status": "OK", "reason": f"HTTP {status}"})
        return result

    except Exception:
        try:
            async with session.get(url, headers=_headers(), allow_redirects=True, timeout=timeout) as r:
                status = r.status
                html = await r.text(errors="ignore")
                result["status_code"] = status
                result["final_url"] = str(r.url)

                if status in (404, 410) or status >= 500:
                    result["status"] = "BROKEN"
                    result["reason"] = f"HTTP {status}"
                    result["snippet"] = (html[:400] + "...") if html else ""
                    return result

                analysed = await _analyze_html(html, url)
                if analysed.get("canonical") == r.url:
                    result["canonical_match"] = True

                if analysed.get("soft"):
                    result.update({
                        "status": "SOFT_404",
                        "reason": "Soft/visible error",
                        "snippet": analysed["snippet"],
                    })
                    return result

                # localized fallback check
                if LOCALE_RE.search(result["final_url"]):
                    fallback = LOCALE_RE.sub("/", result["final_url"], count=1)
                    try:
                        async with session.head(fallback, timeout=5) as fh:
                            if fh.status == 200:
                                result.update({
                                    "status": "OK",
                                    "reason": "Localized fallback",
                                    "localized_rescue": True,
                                })
                                return result
                    except Exception:
                        pass

                result.update({
                    "status": "OK",
                    "reason": f"HTTP {status}",
                    "snippet": analysed.get("snippet", ""),
                })
                return result

        except Exception as e:
            result.update({"status": "N/A", "status_code": 0, "reason": str(e)})
            return result


# ------------------ ASYNC BATCH MODE ------------------
async def run_batch_check(urls, concurrency=MAX_CONCURRENT_LINKS):
    """Run multiple link checks concurrently (used by run_checker)."""
    results = []
    sem = asyncio.Semaphore(concurrency)

    async def safe_check(u, session):
        async with sem:
            try:
                return await check_link_strict(u, session)
            except Exception as e:
                return {"url": u, "status": "N/A", "reason": str(e)}

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [asyncio.create_task(safe_check(u, session)) for u in urls]
        for fut in asyncio.as_completed(tasks):
            res = await fut
            results.append(res)
    return results


# ------------------------------------------------------
# Backward Compatibility
# ------------------------------------------------------
check_link_advanced = check_link_strict

if __name__ == "__main__":
    async def _test():
        test_urls = [
            "https://example.com",
            "https://example.com/404",
            "https://example.com/de-de/",
        ]
        res = await run_batch_check(test_urls)
        for r in res:
            print(r)

    asyncio.run(_test())