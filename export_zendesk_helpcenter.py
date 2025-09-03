# export_zendesk_helpcenter.py
import os, json, time, math, re
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Optional imports for nicer output/markdown & token-aware chunking
try:
    import html2text
    H2T = html2text.HTML2Text()
    H2T.body_width = 0
    H2T.ignore_images = False
    H2T.ignore_links = False
except Exception:
    H2T = None

try:
    import tiktoken
    ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:
    ENCODER = None

ZENDESK_SUBDOMAIN = os.getenv("ZENDESK_SUBDOMAIN")
ZENDESK_EMAIL     = os.getenv("ZENDESK_EMAIL")
ZENDESK_API_TOKEN = os.getenv("ZENDESK_API_TOKEN")

ALLOWED_CATEGORIES = ["eTMF Connect", "RegDocs Connect", "SOP Connect", "Training Connect", "CAPA Connect", "Change Connect", "Supplier Connect", "Audit Connect"]

if not all([ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, ZENDESK_API_TOKEN]):
    raise SystemExit("Missing env vars: ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, ZENDESK_API_TOKEN")

BASE = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com"
AUTH = (ZENDESK_EMAIL, ZENDESK_API_TOKEN)
HEADERS = {"Content-Type": "application/json"}

def html_to_markdown(html: str) -> str:
    # 1) Try html2text (best), else 2) strip tags with BeautifulSoup as fallback
    if H2T:
        return H2T.handle(html or "")
    # Fallback: very basic HTML->text, preserving linebreaks
    soup = BeautifulSoup(html or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all("p"):
        if p.text:
            p.insert_after("\n\n")
    text = soup.get_text()
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def num_tokens(s: str) -> int:
    if ENCODER:
        return len(ENCODER.encode(s))
    # Fallback heuristic: ~4 chars/token
    return max(1, math.ceil(len(s) / 4))

def chunk_text(markdown: str, target_tokens=800, max_tokens=1200) -> List[str]:
    """
    Splits by headings/paragraphs, then packs into chunks near `target_tokens`
    without exceeding `max_tokens`. Works with or without tiktoken.
    """
    # Split by headings and paragraphs to keep semantic units together
    blocks = re.split(r"(\n#{1,6} .*|\n{2,})", markdown)
    # Re-join to keep headings attached to their content
    cleaned_blocks = []
    buf = ""
    for b in blocks:
        if not b:
            continue
        if b.strip().startswith("#"):  # heading
            if buf.strip():
                cleaned_blocks.append(buf)
            buf = b
        else:
            buf += b
    if buf.strip():
        cleaned_blocks.append(buf)

    chunks, cur = [], []
    cur_tokens = 0
    for block in cleaned_blocks:
        btok = num_tokens(block)
        # If a single block is enormous, hard-split by sentences
        if btok > max_tokens:
            sentences = re.split(r"(?<=[.!?])\\s+", block)
            sub = []
            sub_tok = 0
            for s in sentences:
                st = num_tokens(s)
                if sub_tok + st > max_tokens and sub:
                    chunks.append(" ".join(sub).strip())
                    sub, sub_tok = [], 0
                sub.append(s)
                sub_tok += st
            if sub:
                chunks.append(" ".join(sub).strip())
            continue

        if cur_tokens + btok > max_tokens and cur:
            chunks.append("".join(cur).strip())
            cur, cur_tokens = [], 0
        cur.append(block)
        cur_tokens += btok
        if cur_tokens >= target_tokens:
            chunks.append("".join(cur).strip())
            cur, cur_tokens = [], 0

    if cur:
        chunks.append("".join(cur).strip())
    # Final tidy
    return [c.strip() for c in chunks if c and c.strip()]

class ZendeskError(Exception):
    pass

@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception_type(ZendeskError),
)
def get(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    r = requests.get(url, headers=HEADERS, auth=AUTH, params=params, timeout=60)
    if r.status_code == 429:
        # Rate limited — Zendesk returns Retry-After
        retry_after = int(r.headers.get("Retry-After", "5"))
        time.sleep(retry_after)
        raise ZendeskError("Rate limited")
    if not r.ok:
        raise ZendeskError(f"GET {url} -> {r.status_code}: {r.text[:300]}")
    return r.json()

def paginate(url: str, key: str) -> List[Dict[str, Any]]:
    out = []
    next_page = url
    while next_page:
        data = get(next_page)
        out.extend(data.get(key, []))
        next_page = data.get("next_page")
    return out

def fetch_categories() -> Dict[int, Dict[str, Any]]:
    cats = paginate(f"{BASE}/api/v2/help_center/categories.json", "categories")
    return {c["id"]: c for c in cats}

def fetch_sections() -> Dict[int, Dict[str, Any]]:
    secs = paginate(f"{BASE}/api/v2/help_center/sections.json", "sections")
    return {s["id"]: s for s in secs}

def fetch_articles() -> List[Dict[str, Any]]:
    return paginate(f"{BASE}/api/v2/help_center/articles.json?include=users", "articles")

def fetch_translations(article_id: int) -> List[Dict[str, Any]]:
    # Returns body/title per locale
    try:
        t = get(f"{BASE}/api/v2/help_center/articles/{article_id}/translations.json")
        return t.get("translations", [])
    except Exception:
        return []

def fetch_attachments(article_id: int) -> List[Dict[str, Any]]:
    try:
        a = get(f"{BASE}/api/v2/help_center/articles/{article_id}/attachments.json")
        return a.get("article_attachments", [])
    except Exception:
        return []

def build_breadcrumb(article: Dict[str, Any], sections: Dict[int, Dict[str, Any]], categories: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    sec = sections.get(article.get("section_id"))
    cat = categories.get(sec["category_id"]) if sec else None
    return {
        "category_id": cat["id"] if cat else None,
        "category_name": cat["name"] if cat else None,
        "section_id": sec["id"] if sec else None,
        "section_name": sec["name"] if sec else None,
    }

def normalize_article_record(a: Dict[str, Any], translations: List[Dict[str, Any]], sections: Dict[int, Dict[str, Any]], categories: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    base_meta = {
        "article_id": a["id"],
        "article_html_url": a.get("html_url"),
        "title": a.get("title"),
        "locale": a.get("locale"),
        "labels": a.get("label_names", []),
        "draft": a.get("draft", False),
        "promoted": a.get("promoted", False),
        "position": a.get("position"),
        "author_id": a.get("author_id"),
        "permissions": a.get("permission_group_id"),
        "created_at": a.get("created_at"),
        "updated_at": a.get("updated_at"),
        "outdated": a.get("outdated", False),
        "comments_disabled": a.get("comments_disabled", True),
        "user_segment_id": a.get("user_segment_id"),
        "source_locale": a.get("source_locale"),
    }
    bc = build_breadcrumb(a, sections, categories)

    # Pull attachments metadata
    atts = fetch_attachments(a["id"])
    attachments = [
        {
            "id": att.get("id"),
            "file_name": att.get("file_name"),
            "content_type": att.get("content_type"),
            "content_url": att.get("content_url"),
            "size": att.get("size"),
        }
        for att in atts
    ]

    records = []

    # The base article is already one locale; include all available translations
    # and mark which one is the "source" (original)
    trans_map = {(t["locale"]): t for t in translations} if translations else {}
    locales = {a.get("locale")} | set(trans_map.keys())

    for loc in locales:
        t = trans_map.get(loc)
        title = (t.get("title") if t else None) or a.get("title")
        body  = (t.get("body") if t else None) or a.get("body") or ""
        md = html_to_markdown(body)

        rec = {
            **base_meta,
            **bc,
            "locale": loc,
            "title": title,
            "body_html": body,
            "body_markdown": md,
            "attachments": attachments,
            "url": f'{BASE}/hc/{loc}/articles/{a["id"]}',
        }
        records.append(rec)

    return records

def main():
    os.makedirs("zendesk_export", exist_ok=True)
    articles_out = open("zendesk_export/articles.jsonl", "w", encoding="utf-8")
    chunks_out   = open("zendesk_export/chunks.jsonl", "w", encoding="utf-8")

    print("Fetching categories/sections/articles…")
    cats = fetch_categories()
    secs = fetch_sections()
    arts = fetch_articles()
    print(f"Found {len(cats)} categories, {len(secs)} sections, {len(arts)} articles")

    for i, a in enumerate(arts, start=1):
        try:
            trans = fetch_translations(a["id"])
            per_locale = normalize_article_record(a, trans, secs, cats)

             # --- Filtering step ---
        section_obj = secs.get(a.get("section_id"))
        cat = cats.get(section_obj["category_id"]) if section_obj else {}
        category = cat.get("name", "")
        section = section_obj.get("name", "") if section_obj else ""

        if category not in ALLOWED_CATEGORIES and section not in ALLOWED_SECTIONS:
            continue  # Skip this article
        # -----------------------

            for rec in per_locale:
                # Write the full-article record
                articles_out.write(json.dumps(rec, ensure_ascii=False) + "\\n")

                # Chunk for RAG
                chunks = chunk_text(rec["body_markdown"], target_tokens=800, max_tokens=1200)
                for idx, chunk in enumerate(chunks):
                    chunk_rec = {
                        "doc_id": f'{rec["article_id"]}:{rec["locale"]}',
                        "chunk_id": f'{rec["article_id"]}:{rec["locale"]}:{idx}',
                        "title": rec["title"],
                        "url": rec["url"],
                        "locale": rec["locale"],
                        "category_name": rec["category_name"],
                        "section_name": rec["section_name"],
                        "labels": rec["labels"],
                        "created_at": rec["created_at"],
                        "updated_at": rec["updated_at"],
                        "draft": rec["draft"],
                        "outdated": rec["outdated"],
                        "text": chunk,
                        # Helpful for hybrid search:
                        "breadcrumbs": " > ".join([x for x in [rec["category_name"], rec["section_name"], rec["title"]] if x]),
                    }
                    chunks_out.write(json.dumps(chunk_rec, ensure_ascii=False) + "\\n")

            if i % 25 == 0:
                print(f"Processed {i}/{len(arts)} articles…")
                time.sleep(0.2)  # be polite

        except Exception as e:
            print(f"Error on article {a.get('id')}: {e}")
            continue

    articles_out.close()
    chunks_out.close()
    print("Done. Files written to ./zendesk_export/ (articles.jsonl, chunks.jsonl)")

if __name__ == "__main__":
    main()
