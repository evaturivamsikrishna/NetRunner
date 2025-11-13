# src/checker.py
"""
NetRunner — Checker v12 (TRACE mode)

Features:
 - Async extraction of links from pages (aiohttp + BeautifulSoup)
 - Highly-parallel validation with per-domain semaphores
 - HEAD -> GET fallback, JS fallback delegated to validator
 - Batching to avoid memory explosion
 - UVLoop optional acceleration
 - Extensive logging:
     - TRACE-level logs per link (very verbose)
     - DEBUG file (rotating): structured JSON-like lines for post-mortem
     - INFO in console for progress and milestones
 - Safe multiprocessing wrapper (run_checker)
 - Returns: (broken_path, broken_list, all_links, duration_seconds)
"""

from __future__ import annotations

import os
import time
import csv
import json
import asyncio
import logging
import math
from typing import List, Dict, Tuple, Any
from urllib.parse import urljoin, urlparse

import aiohttp
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup

# Local validator (advanced rules)
from src.validators.advanced_link_checker import check_link_strict
from src.logger import get_logger

# ---------------------------------------------------------------------
# Optional uvloop for speed
# ---------------------------------------------------------------------
try:
    import uvloop

    uvloop.install()
except Exception:
    # uvloop not mandatory
    pass

# ---------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------
# Add TRACE numeric level (below DEBUG)
TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")


def trace(self, msg, *args, **kwargs):
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, msg, args, **kwargs)


logging.Logger.trace = trace  # type: ignore

# Get logger and add rotating file handler for debug-heavy logs
logger = get_logger("netrunner.checker", level="INFO")
# Add a dedicated debug file handler if not present
if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
    try:
        from logging.handlers import RotatingFileHandler

        log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        fh = RotatingFileHandler(
            os.path.join(log_dir, "checker_debug.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(fh)
    except Exception:
        logger.warning("Failed to add rotating file handler for checker debug logs.")

# ---------------------------------------------------------------------
# Tunables (override via environment)
# ---------------------------------------------------------------------
GLOBAL_CONCURRENCY = int(os.getenv("GLOBAL_CONCURRENCY", "200"))  # total concurrent requests
PER_DOMAIN_CONCURRENCY = int(os.getenv("PER_DOMAIN_CONCURRENCY", "8"))  # per-domain
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "400"))  # gather tasks in chunks
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))  # seconds
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
)

# Skip common binary/static extensions early
SKIP_EXT = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".mp4",
    ".zip",
    ".webp",
    ".svg",
    ".gif",
    ".woff",
    ".ttf",
    ".css",
    ".js",
)


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return "unknown"


def should_skip(url: str) -> bool:
    if not url:
        return True
    u = url.lower().split("?")[0].split("#")[0]
    for ext in SKIP_EXT:
        if u.endswith(ext):
            return True
    if u.startswith(("mailto:", "tel:", "javascript:")):
        return True
    return False


def now_ms() -> float:
    return time.time() * 1000.0


# ---------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------
async def fetch_page_links(session: aiohttp.ClientSession, page_url: str, page_timeout: int = REQUEST_TIMEOUT) -> List[Dict[str, Any]]:
    """
    Fetch a page and extract link candidates (a, button href).
    Returns list of dict entries with source_page, element, anchor_text, url
    """
    try:
        async with session.get(page_url, timeout=ClientTimeout(total=page_timeout)) as resp:
            status = resp.status
            if status >= 400:
                logger.trace("fetch_page_links → page %s returned status %s", page_url, status)
                return []
            html = await resp.text(errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            items = []
            for tag in soup.find_all(["a", "button"]):
                href = tag.get("href")
                if not href:
                    continue
                if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue
                try:
                    full = urljoin(page_url, href)
                except Exception:
                    continue
                if should_skip(full):
                    logger.trace("fetch_page_links → skipping static resource %s from %s", full, page_url)
                    continue
                items.append({
                    "source_page": page_url,
                    "element": tag.name,
                    "anchor_text": (tag.get_text(strip=True) or "")[:160],
                    "url": full,
                })
            logger.debug("fetch_page_links → %s extracted %d links", page_url, len(items))
            # TRACE each extracted link (very verbose)
            for it in items:
                logger.trace("EXTRACT %s <- %s", it["url"], page_url)
            return items
    except Exception as exc:
        logger.debug("fetch_page_links → failed %s : %s", page_url, exc)
        logger.trace("fetch_page_links exception", exc_info=True)
        return []


# ---------------------------------------------------------------------
# Fast validator wrapping advanced checker
# ---------------------------------------------------------------------
async def validate_link(session: aiohttp.ClientSession, url: str, domain_locks: dict, timeout_sec: int = REQUEST_TIMEOUT) -> Dict[str, Any]:
    """
    High-throughput wrapper that:
     - picks per-domain semaphore
     - tries HEAD first for internal pages, then GET
     - calls check_link_strict (the advanced validator) passing async_resp when available
    Returns the validator result dict or minimal error dict.
    """
    dom = domain_of(url)
    sem: asyncio.Semaphore = domain_locks.setdefault(dom, asyncio.Semaphore(PER_DOMAIN_CONCURRENCY))

    start = now_ms()
    async with sem:
        try:
            # Best-effort: HEAD for same-host resources (heuristic), GET otherwise
            use_head = ("kwalee.com" in dom) or ("localhost" in dom) or ("127.0.0.1" in dom)
            # Attempt HEAD then fallback to GET
            if use_head:
                try:
                    async with session.head(url, allow_redirects=True, timeout=ClientTimeout(total=timeout_sec)) as resp:
                        res = await check_link_strict(url, session=session, async_resp=resp)
                        res["_timing_ms"] = now_ms() - start
                        logger.trace("VALID HEAD %s -> %s", url, res.get("status"))
                        logger.debug(json.dumps({
                            "phase": "head",
                            "url": url,
                            "status_code": getattr(resp, "status", None),
                            "t_ms": res["_timing_ms"],
                        }))
                        return res
                except Exception:
                    # fall through to GET
                    pass

            # GET fallback
            async with session.get(url, allow_redirects=True, timeout=ClientTimeout(total=timeout_sec)) as resp:
                res = await check_link_strict(url, session=session, async_resp=resp)
                res["_timing_ms"] = now_ms() - start
                logger.trace("VALID GET %s -> %s", url, res.get("status"))
                logger.debug(json.dumps({
                    "phase": "get",
                    "url": url,
                    "status_code": getattr(resp, "status", None),
                    "t_ms": res["_timing_ms"],
                }))
                return res

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            dur = now_ms() - start
            logger.trace("VALID ERROR %s -> %s (%.1fms)", url, exc, dur)
            err = {"url": url, "status": "N/A", "status_code": 0, "reason": str(exc), "_timing_ms": dur}
            logger.debug(json.dumps({"phase": "error", "url": url, "error": str(exc), "t_ms": dur}))
            return err


# ---------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------
def safe_write_csv(path: str, rows: List[Dict[str, Any]], fields: List[str]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for r in rows:
                out = {k: (r.get(k, "") if r.get(k, "") is not None else "") for k in fields}
                writer.writerow(out)
    except Exception as exc:
        logger.exception("safe_write_csv failed %s -> %s", path, exc)


# ---------------------------------------------------------------------
# Main async runner (v12) — optimized, batched, traced
# ---------------------------------------------------------------------
async def run_checker_async(urls: List[str], output_dir: str = "data/reports", max_concurrency: int = None) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    Async runner that extracts links from `urls`, validates them, writes CSVs.
    Returns: (broken_path, broken_list, all_links, duration_seconds)
    """
    start = time.time()
    max_concurrency = max_concurrency or GLOBAL_CONCURRENCY
    os.makedirs(output_dir, exist_ok=True)

    conn = aiohttp.TCPConnector(limit=max_concurrency, ttl_dns_cache=300, enable_cleanup_closed=True)
    timeout = ClientTimeout(total=REQUEST_TIMEOUT)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

    logger.info("run_checker_async → starting: pages=%d max_concurrency=%d batch_size=%d", len(urls), max_concurrency, BATCH_SIZE)
    logger.debug("run_checker_async → headers: %s", {k: headers[k] for k in ("User-Agent", "Accept-Language")})

    async with aiohttp.ClientSession(connector=conn, headers=headers, timeout=timeout) as session:
        # 1) extract links concurrently (bounded by number of pages)
        extract_tasks = [fetch_page_links(session, u) for u in urls]
        # Kick off extracts in batches to avoid huge concurrency on enormous page lists
        extracted: List[Dict[str, Any]] = []
        for i in range(0, len(extract_tasks), max(1, BATCH_SIZE)):
            batch = extract_tasks[i:i + BATCH_SIZE]
            logger.info("run_checker_async → extracting batch %d/%d (pages %d)", (i // BATCH_SIZE) + 1, math.ceil(len(extract_tasks) / BATCH_SIZE), len(batch))
            res = await asyncio.gather(*batch, return_exceptions=False)
            for sub in res:
                extracted.extend(sub if isinstance(sub, list) else [])
            logger.debug("run_checker_async → extracted so far %d links", len(extracted))

        # de-dup by URL (normalized)
        normalized = {}
        for l in extracted:
            url_key = (l.get("url") or "").rstrip("/")
            if not url_key:
                continue
            # keep first occurrence metadata
            if url_key not in normalized:
                normalized[url_key] = l
        all_links = list(normalized.values())
        logger.info("run_checker_async → total unique links to validate: %d", len(all_links))

        # 2) validation: prepare validators (no immediate scheduling explosion)
        domain_locks: Dict[str, asyncio.Semaphore] = {}
        validators = [validate_link(session, l["url"], domain_locks) for l in all_links]

        results: List[Dict[str, Any]] = []
        total = len(validators)
        if total == 0:
            logger.info("run_checker_async → no links found, skipping validation.")
        else:
            batches = math.ceil(total / BATCH_SIZE)
            for i in range(0, total, BATCH_SIZE):
                chunk = validators[i:i + BATCH_SIZE]
                logger.info("run_checker_async → validating batch %d/%d (links %d)", (i // BATCH_SIZE) + 1, batches, len(chunk))
                chunk_res = await asyncio.gather(*chunk, return_exceptions=False)
                # record per-link TRACE and append
                for r in chunk_res:
                    # r may be None or dict
                    if not r:
                        continue
                    # Per-link trace (very verbose) — include minimal structured info
                    try:
                        trace_payload = {
                            "url": r.get("url"),
                            "status": r.get("status"),
                            "status_code": r.get("status_code"),
                            "reason": r.get("reason", "")[:200],
                            "timing_ms": r.get("_timing_ms", None),
                        }
                        logger.trace("LINK %s", json.dumps(trace_payload, ensure_ascii=False))
                    except Exception:
                        logger.trace("LINK (unserializable) %s", str(r)[:200])
                    results.append(r)
                logger.info("run_checker_async → batch %d complete (validated %d links total so far)", (i // BATCH_SIZE) + 1, len(results))

        # collect broken items
        broken = [r for r in results if r and r.get("status") == "BROKEN"]
        duration = time.time() - start

    # CSV outputs
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    broken_path = os.path.join(output_dir, f"broken_links_{timestamp}.csv")
    latest_path = os.path.join(output_dir, "broken_links_latest.csv")

    fields = sorted([
        "source_page",
        "element",
        "anchor_text",
        "url",
        "final_url",
        "status",
        "status_code",
        "reason",
        "snippet",
        "localized_rescue",
        "canonical_match",
        "js_recovery",
    ])

    logger.info("run_checker_async → writing CSVs: %s (broken=%d)", broken_path, len(broken))
    safe_write_csv(broken_path, broken, fields)
    safe_write_csv(latest_path, broken, fields)

    logger.info("run_checker_async → finished: links=%d broken=%d duration=%.2fs", len(all_links), len(broken), duration)
    return broken_path, broken, all_links, duration


# ---------------------------------------------------------------------
# Multiprocessing-safe sync wrapper (for ProcessPoolExecutor)
# ---------------------------------------------------------------------
def run_checker(urls: List[str], output_dir: str = "data/reports", max_concurrency: int = None) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    Sync wrapper to call run_checker_async inside a fresh event loop.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(run_checker_async(urls, output_dir, max_concurrency or GLOBAL_CONCURRENCY))
    finally:
        try:
            loop.close()
        except Exception:
            pass