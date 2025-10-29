# src/utils/dedup.py
# ============================================================
# 🔁 URL De-duplication Utility
# Removes duplicate URLs before link checking
# ============================================================

import re

def normalize_url(url: str) -> str:
    """
    Normalizes a URL for deduplication:
    - Strips whitespace and trailing slashes
    - Converts to lowercase
    - Removes URL fragments (#...) and query params if identical base URLs exist
    """
    url = url.strip().lower()
    url = re.sub(r"#.*$", "", url)  # remove fragments
    url = re.sub(r"\?.*$", "", url)  # remove query params (optional)
    if url.endswith("/"):
        url = url[:-1]
    return url


def remove_duplicate_urls(urls: list[str]) -> list[str]:
    """
    Removes duplicate and equivalent URLs efficiently.
    Logs how many were removed for visibility.
    """
    seen = set()
    unique = []
    for url in urls:
        norm = normalize_url(url)
        if norm not in seen:
            seen.add(norm)
            unique.append(url)
    return unique