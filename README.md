# Help Center Public Mirror (Zendesk → Static Site)

This repository publishes a **public mirror** of your Zendesk Help Center so an AI copilot can crawl it.

## What it does
- Exports articles (including translations, labels, breadcrumbs) via Zendesk Help Center API
- Converts HTML → Markdown and builds a static website (MkDocs)
- Deploys automatically to **GitHub Pages**
- Provides a `sitemap.xml` you can feed to your copilot

---

## One-time setup (no coding required)

1. **Create a new private repo** in GitHub and upload these files.
2. Go to **Settings → Secrets and variables → Actions → New repository secret**, add:
   - `ZENDESK_SUBDOMAIN` (e.g., `acme` if your URL is `https://acme.zendesk.com`)
   - `ZENDESK_EMAIL` (use your email with `/token`, e.g., `you@company.com/token`)
   - `ZENDESK_API_TOKEN` (create in Zendesk Admin Center → Apps & Integrations → API → Add API token)
3. Go to **Settings → Pages**, set:
   - **Source**: Deploy from branch → `gh-pages` branch
4. Run the workflow once:
   - Go to **Actions → Publish KB Mirror → Run workflow**

When it finishes:
- Your site will be live at `https://<your-org>.github.io/<repo-name>/`
- The sitemap will be at `https://<your-org>.github.io/<repo-name>/sitemap.xml`

**Give your copilot the sitemap URL** to crawl all articles.

---

## Safety & scope

- Keep the repository **Private**; the **site** is public (GitHub Pages).
- Review content before sharing sitemap with external tools.
- To restrict scope, add an allowlist filter inside the build scripts (optional, see comments).

---

## Maintenance
- The site updates nightly (03:00 UTC). You can also run **Actions → Run workflow** anytime.
- If you change article visibility or add content, the next run will pull it.

---

## Troubleshooting
- **No pages?** Check that your secrets are set and valid, and that your Help Center has published articles.
- **Broken images?** Attachments hot-link to Zendesk by default. If needed, extend the exporter to download attachments and rewrite links.
- **404 on Pages?** Ensure **Settings → Pages** is set to the `gh-pages` branch and the Action has run successfully.
