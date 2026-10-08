#!/usr/bin/env python3
"""Login to Tilda, push blog HTML into T123, set SEO fields, publish, create new pages."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "html"
PAGEIDS_PATH = ROOT / "pageids.json"
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
PAGEIDS = json.loads(PAGEIDS_PATH.read_text(encoding="utf-8"))
PROJECT_ID = "14431186"
OUT = Path("/opt/cursor/artifacts/qp-seo-deep")
OUT.mkdir(parents=True, exist_ok=True)
CDP = "http://127.0.0.1:9222"

EMAIL = os.environ["TILDA_EMAIL"]
PASSWORD = os.environ["TILDA_PASSWORD"]


def slug_meta(slug: str) -> dict:
    if slug == "blog":
        return MANIFEST["hub"]
    for a in MANIFEST["articles"]:
        if a["slug"] == slug:
            return a
    raise KeyError(slug)


def html_for(slug: str) -> str:
    name = "blog.html" if slug == "blog" else f"{slug}.html"
    return (HTML / name).read_text(encoding="utf-8")


def ensure_login(page) -> None:
    page.goto("https://tilda.ru/login/", wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    if "projects" in page.url or "dashboard" in page.url:
        return
    # already logged?
    page.goto("https://tilda.ru/projects/", wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    if "login" not in page.url and "auth" not in page.url:
        return

    page.goto("https://tilda.ru/login/", wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    # fill form
    email_sel = 'input[name="email"], input[type="email"], input#email'
    pass_sel = 'input[name="password"], input[type="password"], input#password'
    page.wait_for_selector(email_sel, timeout=30000)
    page.fill(email_sel, EMAIL)
    page.fill(pass_sel, PASSWORD)
    page.screenshot(path=str(OUT / "login-filled.png"))
    # submit
    for sel in ['button[type="submit"]', 'input[type="submit"]', 'button:has-text("Войти")', 'a:has-text("Войти")']:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.click()
            break
    else:
        page.keyboard.press("Enter")
    page.wait_for_timeout(5000)
    page.screenshot(path=str(OUT / "login-after.png"))
    # navigate projects
    page.goto("https://tilda.ru/projects/", wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    if "login" in page.url:
        raise RuntimeError(f"Tilda login failed: {page.url}")


def open_editor(page, pageid: str) -> None:
    page.goto(
        f"https://tilda.ru/page/?pageid={pageid}&projectid={PROJECT_ID}",
        wait_until="domcontentloaded",
        timeout=90000,
    )
    page.wait_for_timeout(4000)


def save_record_html(page, recid: str, html: str) -> dict:
    """Save T123 HTML via Tilda page API from within editor session."""
    return page.evaluate(
        """async ({recid, html}) => {
          const tryUrls = [
            '/page/submit/',
            '/api/page/submit/',
            '/zero/submit/',
          ];
          // Preferred: use td / page records API if present
          const out = {attempts: []};
          if (typeof window.td !== 'undefined' && window.td && window.td.records) {
            out.td_records = Object.keys(window.td.records || {}).slice(0, 20);
          }
          // Classic savehtml endpoint used by HTML block editor
          const body = new URLSearchParams();
          body.set('comm', 'savehtml');
          body.set('recordid', recid);
          body.set('html', html);
          body.set('pageid', String(window.pageid || (window.td && window.td.pageid) || ''));
          body.set('projectid', String(window.projectid || (window.td && window.td.projectid) || ''));
          try {
            const r = await fetch('/page/submit/', {
              method: 'POST',
              headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
              body: body.toString(),
              credentials: 'same-origin',
            });
            const text = await r.text();
            out.save = {status: r.status, text: text.slice(0, 500)};
            try { out.save.json = JSON.parse(text); } catch(e) {}
          } catch (e) {
            out.save = {error: String(e)};
          }
          return out;
        }""",
        {"recid": str(recid), "html": html},
    )


def set_seo(page, pageid: str, meta: dict) -> dict:
    """Update page SEO title/description/alias via settings if possible."""
    page.goto(
        f"https://tilda.ru/page/?pageid={pageid}&projectid={PROJECT_ID}",
        wait_until="domcontentloaded",
        timeout=90000,
    )
    page.wait_for_timeout(2000)
    return page.evaluate(
        """async ({meta}) => {
          const pageid = String(window.pageid || (window.td && window.td.pageid) || '');
          const projectid = String(window.projectid || (window.td && window.td.projectid) || '');
          const body = new URLSearchParams();
          body.set('comm', 'savepage');
          body.set('pageid', pageid);
          body.set('projectid', projectid);
          if (meta.title) body.set('title', meta.title);
          if (meta.description) body.set('description', meta.description);
          if (meta.keywords) body.set('keywords', meta.keywords);
          // also common field names
          if (meta.title) body.set('pagetitle', meta.title);
          if (meta.description) body.set('pagedescr', meta.description);
          try {
            const r = await fetch('/page/submit/', {
              method: 'POST',
              headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
              body: body.toString(),
              credentials: 'same-origin',
            });
            const text = await r.text();
            let json = null;
            try { json = JSON.parse(text); } catch(e) {}
            return {status: r.status, text: text.slice(0, 400), json};
          } catch (e) {
            return {error: String(e)};
          }
        }""",
        {"meta": meta},
    )


def publish_page(page) -> dict:
    return page.evaluate(
        """async () => {
          const out = {fns: Object.keys(window).filter(k => /Publish/i.test(k)).slice(0, 30)};
          if (typeof window.tp__pagePublish === 'function') {
            try {
              window.tp__pagePublish();
              out.called = 'tp__pagePublish';
            } catch (e) {
              out.call_error = String(e);
            }
          }
          // fallback submit
          try {
            const pageid = String(window.pageid || (window.td && window.td.pageid) || '');
            const projectid = String(window.projectid || (window.td && window.td.projectid) || '');
            const body = new URLSearchParams();
            body.set('comm', 'publish');
            body.set('pageid', pageid);
            body.set('projectid', projectid);
            const r = await fetch('/page/submit/', {
              method: 'POST',
              headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
              body: body.toString(),
              credentials: 'same-origin',
            });
            const text = await r.text();
            out.publish = {status: r.status, text: text.slice(0, 400)};
            try { out.publish.json = JSON.parse(text); } catch(e) {}
          } catch (e) {
            out.publish = {error: String(e)};
          }
          return out;
        }"""
    )


def create_page(page, slug: str, title: str) -> dict:
    """Create a new page in the project; return pageid if possible."""
    page.goto(
        f"https://tilda.ru/projects/settings/?projectid={PROJECT_ID}",
        wait_until="domcontentloaded",
        timeout=90000,
    )
    page.wait_for_timeout(2000)
    # go to project pages list
    page.goto(
        f"https://tilda.ru/projects/?projectid={PROJECT_ID}",
        wait_until="domcontentloaded",
        timeout=90000,
    )
    page.wait_for_timeout(3000)
    page.screenshot(path=str(OUT / f"project-{slug}.png"))

    created = page.evaluate(
        """async ({slug, title, projectid}) => {
          const attempts = [];
          // Tilda create page API variants
          for (const comm of ['addpage', 'newpage', 'createpage']) {
            const body = new URLSearchParams();
            body.set('comm', comm);
            body.set('projectid', projectid);
            body.set('title', title);
            body.set('alias', slug);
            body.set('pagealias', slug);
            try {
              const r = await fetch('/page/submit/', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                body: body.toString(),
                credentials: 'same-origin',
              });
              const text = await r.text();
              let json = null;
              try { json = JSON.parse(text); } catch(e) {}
              attempts.push({comm, status: r.status, text: text.slice(0, 500), json});
              if (json && (json.pageid || (json.data && json.data.pageid) || json.r === 'OK')) {
                return {ok: true, attempts, json};
              }
            } catch (e) {
              attempts.push({comm, error: String(e)});
            }
          }
          // projects submit
          for (const url of ['/projects/submit/', '/page/submit/']) {
            const body = new URLSearchParams();
            body.set('comm', 'addpage');
            body.set('projectid', projectid);
            body.set('title', title);
            body.set('alias', slug);
            try {
              const r = await fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                body: body.toString(),
                credentials: 'same-origin',
              });
              const text = await r.text();
              let json = null;
              try { json = JSON.parse(text); } catch(e) {}
              attempts.push({url, status: r.status, text: text.slice(0, 500), json});
              if (json && (json.pageid || json.r === 'OK')) {
                return {ok: true, attempts, json};
              }
            } catch (e) {
              attempts.push({url, error: String(e)});
            }
          }
          return {ok: false, attempts};
        }""",
        {"slug": slug, "title": title, "projectid": PROJECT_ID},
    )
    return created


def add_html_block(page, pageid: str, html: str) -> dict:
    """Add T123 HTML record to a page."""
    open_editor(page, pageid)
    return page.evaluate(
        """async ({html, pageid}) => {
          const projectid = String(window.projectid || (window.td && window.td.projectid) || '');
          const body = new URLSearchParams();
          body.set('comm', 'addrecord');
          body.set('pageid', pageid);
          body.set('projectid', projectid);
          body.set('typeid', '131'); // HTML
          body.set('html', html);
          try {
            const r = await fetch('/page/submit/', {
              method: 'POST',
              headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
              body: body.toString(),
              credentials: 'same-origin',
            });
            const text = await r.text();
            let json = null;
            try { json = JSON.parse(text); } catch(e) {}
            return {status: r.status, text: text.slice(0, 600), json};
          } catch (e) {
            return {error: String(e)};
          }
        }""",
        {"html": html, "pageid": str(pageid)},
    )


def main() -> None:
    results = {"pages": {}, "created": {}}
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        context = browser.contexts[0]
        page = context.new_page()
        page.set_default_timeout(90000)

        ensure_login(page)
        page.screenshot(path=str(OUT / "projects.png"))
        results["logged_in"] = page.url

        # Probe save on existing page
        open_editor(page, PAGEIDS["blog-fizlicam"]["pageid"])
        probe = page.evaluate(
            """() => ({
              href: location.href,
              pageid: window.pageid || (window.td && window.td.pageid) || null,
              projectid: window.projectid || (window.td && window.td.projectid) || null,
              hasPublish: typeof window.tp__pagePublish,
              tdKeys: window.td ? Object.keys(window.td).slice(0, 40) : [],
              recordTypes: window.td && window.td.records ? Object.values(window.td.records).map(r => ({id:r.id||r.recordid, type:r.type||r.typeid})).slice(0, 20) : [],
            })"""
        )
        (OUT / "probe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
        results["probe"] = probe

        # Update existing pages
        existing = ["blog"] + [
            k for k in PAGEIDS.keys()
            if k.startswith("blog-") and isinstance(PAGEIDS[k], dict) and "pageid" in PAGEIDS[k]
        ]
        # hub key is 'hub'
        existing_map = {"blog": PAGEIDS["hub"]}
        for k, v in PAGEIDS.items():
            if k.startswith("blog-") and isinstance(v, dict) and "pageid" in v:
                existing_map[k] = v

        for slug, ids in existing_map.items():
            meta = slug_meta(slug if slug != "blog" else "blog")
            html = html_for(slug if slug != "blog" else "blog")
            open_editor(page, ids["pageid"])
            save = save_record_html(page, ids["recid"], html)
            seo = set_seo(page, ids["pageid"], meta)
            open_editor(page, ids["pageid"])
            pub = publish_page(page)
            # close publish modal if any
            page.wait_for_timeout(2000)
            page.keyboard.press("Escape")
            results["pages"][slug] = {"save": save, "seo": seo, "pub": pub}
            print("UPDATED", slug, save.get("save", {}).get("status"), seo.get("status"))

        # Create new gap pages
        new_slugs = ["blog-reestr", "blog-nalogi", "blog-kontrol", "blog-gph"]
        for slug in new_slugs:
            if slug in PAGEIDS and isinstance(PAGEIDS[slug], dict) and PAGEIDS[slug].get("pageid"):
                continue
            meta = slug_meta(slug)
            created = create_page(page, slug, meta["h1"])
            results["created"][slug] = created
            print("CREATE", slug, created.get("ok"), str(created)[:200])
            pageid = None
            json_ = created.get("json") or {}
            pageid = (
                json_.get("pageid")
                or (json_.get("data") or {}).get("pageid")
                or None
            )
            # parse from attempts
            if not pageid:
                for a in created.get("attempts") or []:
                    j = a.get("json") or {}
                    pageid = j.get("pageid") or (j.get("data") or {}).get("pageid")
                    if pageid:
                        break
                    m = re.search(r"pageid[=\":]+(\d+)", a.get("text") or "")
                    if m:
                        pageid = m.group(1)
                        break
            if not pageid:
                continue
            add = add_html_block(page, str(pageid), html_for(slug))
            recid = None
            j2 = add.get("json") or {}
            recid = j2.get("recordid") or j2.get("recid") or (j2.get("data") or {}).get("recordid")
            seo = set_seo(page, str(pageid), meta)
            open_editor(page, str(pageid))
            pub = publish_page(page)
            page.wait_for_timeout(2000)
            page.keyboard.press("Escape")
            PAGEIDS[slug] = {"pageid": str(pageid), "recid": str(recid) if recid else "", "t966": ""}
            results["pages"][slug] = {"created": True, "add": add, "seo": seo, "pub": pub, "pageid": pageid, "recid": recid}
            print("NEW", slug, pageid, recid)

        PAGEIDS_PATH.write_text(json.dumps(PAGEIDS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (OUT / "publish-results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        page.close()
        print("DONE")


if __name__ == "__main__":
    main()
