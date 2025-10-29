import os
import time
import csv
import asyncio
import aiohttp
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from tqdm import tqdm
from src.logger import get_logger
from src.validators.advanced_link_checker import check_link_strict

logger = get_logger()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}
GLOBAL_CONCURRENCY = 20
PER_DOMAIN_LIMIT = 5
MAX_RETRIES = 2
TIMEOUT = ClientTimeout(total=30)


def normalize_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip().replace("http://", "https://")
    if url.endswith("/"):
        url = url[:-1]
    return url.lower()


def detect_link_type(url: str) -> str:
    if "/blog" in url:
        return "blog"
    elif "/careers" in url:
        return "careers"
    elif "/games" in url:
        return "game"
    elif "/contact" in url:
        return "contact"
    elif any(k in url for k in ["/about", "/company"]):
        return "company"
    return "general"


def get_domain(url):
    try:
        return urlparse(url).netloc
    except Exception:
        return "default"


async def fetch_page_links(session, page_url: str, domain_locks):
    domain = get_domain(page_url)
    lock = domain_locks.setdefault(domain, asyncio.Semaphore(PER_DOMAIN_LIMIT))
    async with lock:
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with session.get(page_url, headers=HEADERS) as resp:
                    if resp.status >= 400:
                        logger.warning(f"[WARN] {page_url} returned {resp.status}")
                        return []
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    links = []
                    for tag in soup.find_all(["a", "button"]):
                        href = tag.get("href")
                        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                            continue
                        full_url = urljoin(page_url, href)
                        links.append({
                            "source_page": page_url,
                            "element": tag.name,
                            "anchor_text": tag.get_text(strip=True)[:120],
                            "url": full_url,
                            "link_type": detect_link_type(full_url),
                        })
                    return links
            except Exception as e:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                logger.error(f"❌ Failed to fetch {page_url}: {e}")
                return []


async def check_link_async(session, url, domain_locks):
    domain = get_domain(url)
    lock = domain_locks.setdefault(domain, asyncio.Semaphore(PER_DOMAIN_LIMIT))
    async with lock:
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with session.head(url, allow_redirects=True) as resp:
                    result = await check_link_strict(url, session=session, async_resp=resp)
                    if result:
                        return result
            except Exception:
                try:
                    async with session.get(url, allow_redirects=True) as resp:
                        result = await check_link_strict(url, session=session, async_resp=resp)
                        if result:
                            return result
                except Exception as e:
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(1.2 * (attempt + 1))
                        continue
                    return {"url": url, "status": "N/A", "status_code": 0, "reason": str(e)}
    return {"url": url, "status": "N/A", "status_code": 0, "reason": "Unknown error"}


async def run_checker_async(urls, output_dir="data/reports"):
    os.makedirs(output_dir, exist_ok=True)
    start = time.time()
    domain_locks = {}
    all_links, invalid_links = [], []

    async with aiohttp.ClientSession(timeout=TIMEOUT, headers=HEADERS) as session:
        print(f"\n🔍 Extracting links from {len(urls)} pages...\n")
        extract_tasks = [fetch_page_links(session, u, domain_locks) for u in urls]
        results = await asyncio.gather(*extract_tasks)
        all_links = [link for sub in results for link in sub]

        print(f"\n🧹 Deduplicating links...\n")
        seen = {}
        for link in all_links:
            norm = normalize_url(link["url"])
            if norm not in seen:
                seen[norm] = link
        all_links = list(seen.values())
        print(f"✅ Deduplicated to {len(all_links)} unique links.\n")

        print(f"🌐 Validating {len(all_links)} links...\n")
        check_tasks = [check_link_async(session, link["url"], domain_locks) for link in all_links]
        for coro in tqdm(asyncio.as_completed(check_tasks), total=len(check_tasks), desc="🧠 Checking", unit="link"):
            result = await coro
            if not result:
                continue
            status = result.get("status")
            code = result.get("status_code", 0)
            if status == "BROKEN" or (code in (404, 410) or 500 <= code < 600):
                invalid_links.append(result)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    valid_path = os.path.join(output_dir, f"valid_links_{timestamp}.csv")
    broken_path = os.path.join(output_dir, f"broken_links_{timestamp}.csv")
    latest_broken_path = os.path.join(output_dir, "broken_links_latest.csv")

    fieldnames = sorted({
        "source_page", "element", "anchor_text", "url", "final_url",
        "status", "status_code", "reason", "link_type", "snippet",
        "localized_rescue", "canonical_match", "js_recovery"
    })

    with open(valid_path, "w", newline="", encoding="utf-8") as vf:
        writer = csv.DictWriter(vf, fieldnames=fieldnames)
        writer.writeheader()
        for link in all_links:
            code = link.get("status_code", 0)
            if link.get("status") not in ("BROKEN", "SOFT_404") and (not code or code < 400):
                writer.writerow(link)

    with open(broken_path, "w", newline="", encoding="utf-8") as bf:
        writer = csv.DictWriter(bf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(invalid_links)

    with open(latest_broken_path, "w", newline="", encoding="utf-8") as lf:
        writer = csv.DictWriter(lf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(invalid_links)

    duration = time.time() - start
    print(f"\n✅ Done in {duration:.1f}s — Checked {len(all_links)} links, Found {len(invalid_links)} broken.")
    logger.info(f"✅ {len(all_links)} links checked — {len(invalid_links)} broken.")
    return broken_path, invalid_links, all_links, duration


def run_checker(urls, output_dir="data/reports"):
    return asyncio.run(run_checker_async(urls, output_dir))