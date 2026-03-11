#!/usr/bin/env python3
import hashlib
import mimetypes
import os
import re
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.request import Request, urlopen

BASE_URL = "http://shishirr.pro.bd/"
ALLOWED_HOST = "shishirr.pro.bd"
OUT_DIR = Path("site")
MAX_URLS = 2000

LINK_RE = re.compile(r'''(?:href|src)=["']([^"'#]+)["']''', re.IGNORECASE)
CSS_URL_RE = re.compile(r"url\(([^)]+)\)", re.IGNORECASE)


def normalize_url(url: str) -> str:
    url, _ = urldefrag(url)
    p = urlparse(url)
    scheme = p.scheme or "http"
    netloc = p.netloc.lower()
    path = p.path or "/"
    query = f"?{p.query}" if p.query else ""
    return f"{scheme}://{netloc}{path}{query}"


def url_to_path(url: str, content_type: str | None) -> Path:
    p = urlparse(url)
    path = p.path
    if not path or path.endswith("/"):
        path = (path or "/") + "index.html"

    ext = Path(path).suffix.lower()
    is_html = content_type and "html" in content_type.lower()
    if is_html and ext == "":
        path = path + ".html"

    if p.query:
        digest = hashlib.md5(p.query.encode("utf-8")).hexdigest()[:8]
        base = Path(path)
        stem = base.stem or "index"
        suffix = base.suffix or ".html"
        path = str(base.with_name(f"{stem}__q_{digest}{suffix}"))

    return OUT_DIR / ALLOWED_HOST / path.lstrip("/")


def should_follow(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return False
    return p.netloc.lower() == ALLOWED_HOST


def extract_links(base_url: str, content: str) -> list[str]:
    links = []

    for raw in LINK_RE.findall(content):
        raw = raw.strip()
        if raw.startswith(("mailto:", "tel:", "javascript:")):
            continue
        links.append(urljoin(base_url, raw))

    for raw in CSS_URL_RE.findall(content):
        raw = raw.strip().strip('"\'')
        if not raw or raw.startswith(("data:", "mailto:", "javascript:")):
            continue
        links.append(urljoin(base_url, raw))

    return links


def fetch(url: str):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; site-cloner/1.0)"})
    with urlopen(req, timeout=30) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()
    return data, content_type


def ensure_parent(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    q = deque([normalize_url(BASE_URL)])
    queued = {normalize_url(BASE_URL)}
    visited = set()
    count = 0

    while q and count < MAX_URLS:
        url = q.popleft()
        if url in visited:
            continue

        visited.add(url)
        count += 1

        try:
            data, content_type = fetch(url)
        except Exception as e:
            print(f"[skip] {url} -> {e}")
            continue

        out_path = url_to_path(url, content_type)
        ensure_parent(out_path)
        out_path.write_bytes(data)
        print(f"[saved] {url} -> {out_path}")

        text_like = any(x in (content_type or "").lower() for x in ["html", "css", "javascript", "text/"])
        if not text_like:
            continue

        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = data.decode("latin-1")
            except Exception:
                continue

        for link in extract_links(url, content):
            norm = normalize_url(link)
            if should_follow(norm) and norm not in visited and norm not in queued:
                q.append(norm)
                queued.add(norm)

    print(f"Done. Visited {len(visited)} URL(s).")


if __name__ == "__main__":
    main()
