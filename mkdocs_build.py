# mkdocs_build.py
import json, os, re, unicodedata, pathlib

def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+","-", s).strip("-").lower()
    return s or "article"

os.makedirs("docs", exist_ok=True)
nav = {}  # {locale: {category: {section: [("Title","path")]}}}

articles_path = "zendesk_export/articles.jsonl"
if not os.path.exists(articles_path):
    raise SystemExit("Expected zendesk_export/articles.jsonl. Run export_zendesk_helpcenter.py first.")

with open(articles_path, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        a = json.loads(line)
        loc = (a.get("locale") or "en-us").lower()
        cat = a.get("category_name") or "Uncategorized"
        sec = a.get("section_name") or "General"
        title = a.get("title") or f'Article {a["article_id"]}'
        md = a.get("body_markdown") or ""
        slug = slugify(title)
        path = f"docs/{loc}/{slugify(cat)}/{slugify(sec)}/{slug}.md"
        pathlib.Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as out:
            out.write("---\n")
            out.write(f'title: "{title}"\n')
            out.write(f"zendesk_url: {a.get('url')}\n")
            out.write(f"article_id: {a.get('article_id')}\n")
            out.write(f"locale: {loc}\n")
            out.write(f"labels: {a.get('labels')}\n")
            out.write(f"updated_at: {a.get('updated_at')}\n")
            out.write(f'breadcrumbs: "{(a.get("category_name") or "")} > {(a.get("section_name") or "")}"\n')
            out.write("---\n\n")
            out.write(md.strip() + "\n")


        nav.setdefault(loc, {}).setdefault(cat, {}).setdefault(sec, []).append((title, path.replace("docs/","")))

# Write mkdocs.yml with nav
with open("mkdocs.yml","w",encoding="utf-8") as cfg:
    cfg.write("site_name: Montrium Help Center (Public Mirror)\\n")
    cfg.write("theme:\\n  name: material\\n")
    cfg.write("plugins:\\n  - search\\n  - sitemap\\n")
    cfg.write("nav:\\n")
    for loc, cats in sorted(nav.items()):
        cfg.write(f"  - {loc}:\\n")
        for cat, secs in sorted(cats.items()):
            cfg.write(f"    - {cat}:\\n")
            for sec, items in sorted(secs.items()):
                cfg.write(f"      - {sec}:\\n")
                for title, path in sorted(items):
                    cfg.write(f'        - \\"{title}\\": \\"{path}\\"\\n')
print("mkdocs.yml written and docs/ populated.")
