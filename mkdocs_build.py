# mkdocs_build.py — robust JSONL reader + YAML-safe quoting + clean nav
import json, os, re, unicodedata, pathlib

# ---------- helpers ----------
def slugify(s: str) -> str:
    s = (s or "article")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "article"

def safe_yaml_str(s: str) -> str:
    """
    Make a string YAML-safe for use inside double quotes.
    YAML escapes a double-quote by doubling it: "".
    Also collapse newlines to spaces.
    """
    if s is None:
        s = ""
    s = str(s)
    s = s.replace('"', '""')
    s = s.replace("\r", " ").replace("\n", " ")
    return s

def iter_jsonl_robust(fp):
    """
    Yields JSON objects from a file intended to be JSONL, tolerating:
    - multiple JSON objects concatenated on one physical line
    - stray non-JSON characters before/after objects
    - embedded whitespace/commas between objects
    """
    dec = json.JSONDecoder()
    for raw in fp:
        s = raw.strip()
        if not s:
            continue
        i, n = 0, len(s)
        while i < n:
            start = s.find("{", i)
            if start == -1:
                break
            try:
                obj, end = dec.raw_decode(s, start)
                yield obj
                i = end
                while i < n and s[i] in " \t\r\n,":
                    i += 1
            except json.JSONDecodeError:
                i = start + 1  # skip this brace and keep scanning

# ---------- main ----------
os.makedirs("docs", exist_ok=True)
nav = {}  # {locale: {category: {section: [(title, path_rel)]}}}

articles_path = "zendesk_export/articles.jsonl"
if not os.path.exists(articles_path):
    raise SystemExit("Expected zendesk_export/articles.jsonl. Run export_zendesk_helpcenter.py first.")

count = 0
with open(articles_path, "r", encoding="utf-8") as f:
    for a in iter_jsonl_robust(f):
        count += 1
        loc = (a.get("locale") or "en-us").lower()
        cat = a.get("category_name") or "Uncategorized"
        sec = a.get("section_name") or "General"
        title = a.get("title") or f'Article {a.get("article_id","")}'
        html = a.get("body_html") or ""

        # Build file path
        path = f"docs/{loc}/{slugify(cat)}/{slugify(sec)}/{slugify(title)}.md"
        pathlib.Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)

        # Front matter (YAML) + content
        with open(path, "w", encoding="utf-8") as out:
            out.write("---\n")
            out.write(f'title: "{safe_yaml_str(title)}"\n')
            out.write(f"zendesk_url: {a.get('url')}\n")
            out.write(f"article_id: {a.get('article_id')}\n")
            out.write(f"locale: {safe_yaml_str(loc)}\n")
            out.write(f"labels: {a.get('labels')}\n")
            out.write(f"updated_at: {safe_yaml_str(a.get('updated_at'))}\n")
            breadcrumbs = f'{a.get("category_name") or ""} > {a.get("section_name") or ""}'
            out.write('<div class="zd-article">\n')
            out.write((html or "").strip())
            out.write("\n</div>\n")

        nav.setdefault(loc, {}).setdefault(cat, {}).setdefault(sec, []).append(
            (title, path.replace("docs/", ""))
        )

# Write mkdocs.yml with fully quoted keys
with open("mkdocs.yml", "w", encoding="utf-8") as cfg:
    cfg.write("site_name: Montrium Help Center (Public Mirror)\n")
    cfg.write('site_url: "https://cmantz23-ship-it.github.io/helpcenter-mirror/"\n')
    cfg.write("theme:\n  name: material\n")
    cfg.write("extra_css:\n  - assets/zd.css\n")
    cfg.write("plugins:\n  - search\n")
    cfg.write("nav:\n")
    for loc, cats in sorted(nav.items()):
        cfg.write(f'  - "{safe_yaml_str(loc)}":\n')
        for cat, secs in sorted(cats.items()):
            cfg.write(f'    - "{safe_yaml_str(cat)}":\n')
            for sec, items in sorted(secs.items()):
                cfg.write(f'      - "{safe_yaml_str(sec)}":\n')
                for title, relpath in sorted(items):
                    cfg.write(f'        - "{safe_yaml_str(title)}": "{safe_yaml_str(relpath)}"\n')

print(f"mkdocs.yml written and docs/ populated with {count} articles.")
