#!/usr/bin/env python3
"""Publish Quantum Payouts blog HTML to Tilda T123 via Ace editor + FormData saverecord."""
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


def meta_for(slug: str) -> dict:
    if slug == "blog":
        return MANIFEST["hub"]
    for a in MANIFEST["articles"]:
        if a["slug"] == slug:
            return a
    raise KeyError(slug)


def html_for(slug: str) -> str:
    return (HTML / ("blog.html" if slug == "blog" else f"{slug}.html")).read_text(encoding="utf-8")


def login(page) -> None:
    page.goto("https://tilda.ru/projects/", wait_until="domcontentloaded", timeout=60000)
    time.sleep(2)
    if "login" not in page.url and "auth" not in page.url:
        return
    page.goto("https://tilda.ru/login/", wait_until="domcontentloaded", timeout=60000)
    time.sleep(1)
    page.fill("#email", EMAIL)
    page.fill("#password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_timeout(6000)
    page.goto("https://tilda.ru/projects/", wait_until="domcontentloaded", timeout=60000)
    time.sleep(2)
    if "login" in page.url:
        raise RuntimeError("login failed")


def open_editor(page, pageid: str) -> None:
    page.goto(
        f"https://tilda.ru/page/?pageid={pageid}&projectid={PROJECT_ID}",
        wait_until="domcontentloaded",
        timeout=90000,
    )
    page.wait_for_timeout(5000)


def open_content_panel(page, recid: str) -> bool:
    if page.evaluate("() => !!document.querySelector('.pe-content-form textarea[name=code]')"):
        return True
    page.evaluate(
        """(recid) => {
          const el = document.getElementById('record'+recid) || document.getElementById('rec'+recid);
          if (el) el.scrollIntoView({block:'center'});
        }""",
        recid,
    )
    page.wait_for_timeout(400)
    try:
        page.locator(f"#record{recid}").hover(force=True, timeout=5000)
    except Exception:
        page.locator(f"#rec{recid}").hover(force=True, timeout=5000)
    page.wait_for_timeout(700)
    infos = page.evaluate(
        """() => [...document.querySelectorAll('button')].filter(b => /Контент/.test(b.innerText||'')).map(b => {
          const r = b.getBoundingClientRect();
          const parent = (b.closest('.tp-record-ui-container')||{}).innerText || '';
          return {x:r.x,y:r.y,w:r.width,h:r.height,parent:parent.slice(0,50)};
        }).filter(i => i.h>0 && i.w>0 && /T123/.test(i.parent))"""
    )
    if not infos:
        return False
    t = infos[0]
    page.mouse.click(t["x"] + t["w"] / 2, t["y"] + t["h"] / 2)
    for _ in range(20):
        if page.evaluate("() => !!document.querySelector('.pe-content-form textarea[name=code]')"):
            return True
        page.wait_for_timeout(400)
    return False


def save_html(page, recid: str, pageid: str, html: str) -> dict:
    if not open_content_panel(page, recid):
        return {"ok": False, "error": "no_content_panel"}
    return page.evaluate(
        """async ({html, recid, pageid}) => {
          const edEl = document.querySelector('.ace_editor');
          if (!edEl || !window.ace) return {ok:false, error:'no_ace'};
          const ed = ace.edit(edEl.id || edEl);
          ed.setValue(html, -1);
          const ta = document.querySelector('textarea[name=code]');
          ta.value = html;

          // Prefer Tilda path
          try {
            const p = edrec__sendForm('save', 'content');
            if (p && typeof p.then === 'function') await p;
            await new Promise(r => setTimeout(r, 2500));
            const still = !!document.querySelector('.pe-content-form');
            // If panel closed, likely saved
            if (!still) return {ok:true, via:'edrec', closed:true};
          } catch (e) {
            /* fall through to raw */
          }

          // Raw multipart fallback
          const fd = new FormData();
          fd.append('comm', 'saverecord');
          fd.append('recordid', recid);
          fd.append('pageid', pageid);
          fd.append('code', html);
          const resp = await fetch('/page/submit/', {method:'POST', body:fd, credentials:'same-origin'});
          const text = await resp.text();
          const ok = resp.status === 200 && (text.trim() === 'OK' || text.trim() === '' || text.includes('"r":"OK"') || text.includes('OK'));
          if (ok && typeof edrec__closeEditForm === 'function') {
            try { edrec__closeEditForm(); } catch (e) {}
          }
          if (ok && typeof tp__updateRecord === 'function') {
            try { tp__updateRecord(recid); } catch (e) {}
          }
          return {ok, via:'formdata', status: resp.status, text: text.slice(0, 300)};
        }""",
        {"html": html, "recid": str(recid), "pageid": str(pageid)},
    )


def set_seo(page, pageid: str, meta: dict) -> dict:
    return page.evaluate(
        """async ({pageid, meta}) => {
          const fd = new FormData();
          fd.append('comm', 'savepage');
          fd.append('pageid', pageid);
          fd.append('projectid', '14431186');
          if (meta.title) { fd.append('title', meta.title); fd.append('pagetitle', meta.title); }
          if (meta.description) { fd.append('description', meta.description); fd.append('pagedescr', meta.description); }
          if (meta.keywords) fd.append('keywords', meta.keywords);
          try {
            const r = await fetch('/page/submit/', {method:'POST', body:fd, credentials:'same-origin'});
            const t = await r.text();
            return {status:r.status, text:t.slice(0,300)};
          } catch (e) {
            return {error:String(e)};
          }
        }""",
        {"pageid": str(pageid), "meta": meta},
    )


def publish_page(page, pageid: str) -> dict:
    # UI publish
    try:
        page.evaluate("() => { if (typeof tp__pagePublish==='function') tp__pagePublish(); }")
        page.wait_for_timeout(4000)
    except Exception as e:
        pass
    # API fallback
    api = page.evaluate(
        """async (pageid) => {
          const fd = new FormData();
          fd.append('comm', 'publish');
          fd.append('pageid', pageid);
          fd.append('projectid', '14431186');
          try {
            const r = await fetch('/page/submit/', {method:'POST', body:fd, credentials:'same-origin'});
            const t = await r.text();
            return {status:r.status, text:t.slice(0,300)};
          } catch (e) {
            return {error:String(e)};
          }
        }""",
        str(pageid),
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    return api


def create_page(page, title: str, alias: str):
    created = page.evaluate(
        """async ({title, alias}) => {
          const fd = new FormData();
          fd.append('comm', 'addpage');
          fd.append('projectid', '14431186');
          fd.append('title', title);
          fd.append('alias', alias);
          fd.append('pagealias', alias);
          const r = await fetch('/page/submit/', {method:'POST', body:fd, credentials:'same-origin'});
          const t = await r.text();
          let json=null; try{json=JSON.parse(t)}catch(e){}
          return {status:r.status, text:t.slice(0,800), json};
        }""",
        {"title": title, "alias": alias},
    )
    pageid = None
    j = created.get("json") or {}
    pageid = j.get("pageid") or (j.get("data") or {}).get("pageid")
    if not pageid:
        m = re.search(r"pageid[\"'=\s:]+(\d{6,})", created.get("text") or "")
        if m:
            pageid = m.group(1)
    return pageid, created


def ensure_t123(page, pageid: str):
    open_editor(page, pageid)
    recid = page.evaluate(
        """() => {
          const rec = document.querySelector('div.record[data-record-type="131"]');
          if (rec && rec.id) return rec.id.replace('record','');
          const all=[...document.querySelectorAll('div.record[id^=record]')].map(r=>({
            id:r.id.replace('record',''), typ:r.getAttribute('data-record-type')
          }));
          const hit=all.find(a=>a.typ==='131');
          return hit?hit.id:null;
        }"""
    )
    if recid:
        return recid, {"existing": True}
    added = page.evaluate(
        """async (pageid) => {
          const fd=new FormData();
          fd.append('comm','addrecord');
          fd.append('pageid', pageid);
          fd.append('projectid','14431186');
          fd.append('typeid','131');
          fd.append('tplid','123');
          const r=await fetch('/page/submit/',{method:'POST',body:fd,credentials:'same-origin'});
          const t=await r.text();
          let json=null; try{json=JSON.parse(t)}catch(e){}
          return {status:r.status, text:t.slice(0,500), json};
        }""",
        str(pageid),
    )
    page.wait_for_timeout(1500)
    open_editor(page, pageid)
    recid = page.evaluate(
        """() => {
          const rec = document.querySelector('div.record[data-record-type="131"]');
          if (rec && rec.id) return rec.id.replace('record','');
          const all=[...document.querySelectorAll('div.record[id^=record]')];
          return all.length?all[all.length-1].id.replace('record',''):null;
        }"""
    )
    return recid, added


def verify_live(page, slug: str, needle: str) -> bool:
    url = f"https://quantumpayouts.ru/{slug if slug!='blog' else 'blog'}?cb={int(time.time())}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    text = page.evaluate("() => document.body.innerText")
    return needle in text


def main() -> None:
    results = {"updated": {}, "created": {}, "errors": [], "verified": {}}
    needles = {
        "blog": "База: контур выплат",
        "blog-fizlicam": "выстроить контур для бизнеса",
        "blog-reestr": "рабочий стандарт для компании",
        "blog-nalogi": "Налоги и учёт при выплатах",
        "blog-kontrol": "что должен видеть руководитель",
        "blog-gph": "платить исполнителям без хаоса",
        "blog-samozanyatye": "операционная модель для компании",
        "blog-sbp": "Когда СБП сильнее карты",
        "blog-1c-api": "Кому какая интеграция",
        "blog-lombardy": "Операционная модель на точке",
        "blog-mfo": "Контур выплаты займа",
        "blog-trade-in": "Сценарий на сделке",
        "blog-vtorsyre": "Процесс у весов",
        "blog-strahovye": "Контур урегулирования",
        "blog-selhoz": "Сезонная операционка",
        "blog-kuriery": "Модель для платформы",
    }

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        context = browser.contexts[0]
        page = context.new_page()
        page.set_default_timeout(90000)
        login(page)

        existing = {"blog": PAGEIDS["hub"]}
        for k, v in PAGEIDS.items():
            if k.startswith("blog-") and isinstance(v, dict) and v.get("pageid") and v.get("recid"):
                existing[k] = v

        for slug, ids in existing.items():
            for attempt in range(1, 4):
                try:
                    open_editor(page, ids["pageid"])
                    save = save_html(page, ids["recid"], ids["pageid"], html_for(slug if slug != "blog" else "blog"))
                    seo = set_seo(page, ids["pageid"], meta_for(slug if slug != "blog" else "blog"))
                    open_editor(page, ids["pageid"])
                    pub = publish_page(page, ids["pageid"])
                    results["updated"][slug] = {"save": save, "seo": seo, "pub": pub, "attempt": attempt}
                    print("UPD", slug, save.get("ok"), save.get("via"), save.get("error"))
                    if save.get("ok"):
                        break
                except Exception as e:
                    results["errors"].append({"slug": slug, "attempt": attempt, "error": str(e)})
                    print("ERR", slug, attempt, e)
                    time.sleep(3)
            (OUT / "publish-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

        for slug in ["blog-reestr", "blog-nalogi", "blog-kontrol", "blog-gph"]:
            if isinstance(PAGEIDS.get(slug), dict) and PAGEIDS[slug].get("pageid") and PAGEIDS[slug].get("recid"):
                # already have ids — update path above if in existing; else update now
                if slug in existing:
                    continue
            try:
                m = meta_for(slug)
                pageid, created = create_page(page, m["h1"], slug)
                results["created"][slug] = {"pageid": pageid, "raw": created}
                if not pageid:
                    print("NO_PAGE", slug, created)
                    continue
                # set alias via seo-ish
                page.evaluate(
                    """async ({pageid, alias}) => {
                      const fd=new FormData();
                      fd.append('comm','savepage');
                      fd.append('pageid', pageid);
                      fd.append('projectid','14431186');
                      fd.append('alias', alias);
                      fd.append('pagealias', alias);
                      await fetch('/page/submit/',{method:'POST',body:fd,credentials:'same-origin'});
                    }""",
                    {"pageid": str(pageid), "alias": slug},
                )
                recid, added = ensure_t123(page, pageid)
                results["created"][slug]["recid"] = recid
                results["created"][slug]["added"] = added
                if not recid:
                    print("NO_REC", slug)
                    continue
                open_editor(page, pageid)
                save = save_html(page, str(recid), str(pageid), html_for(slug))
                seo = set_seo(page, pageid, m)
                open_editor(page, pageid)
                pub = publish_page(page, pageid)
                PAGEIDS[slug] = {"pageid": str(pageid), "recid": str(recid), "t966": ""}
                results["updated"][slug] = {"save": save, "seo": seo, "pub": pub, "new": True}
                print("NEW", slug, pageid, recid, save.get("ok"))
            except Exception as e:
                results["errors"].append({"slug": slug, "error": str(e)})
                print("ERR_NEW", slug, e)

        # verify
        vpage = context.new_page()
        for slug, needle in needles.items():
            try:
                ok = verify_live(vpage, slug, needle)
                results["verified"][slug] = ok
                print("LIVE", slug, ok)
            except Exception as e:
                results["verified"][slug] = f"err:{e}"
        vpage.close()

        PAGEIDS_PATH.write_text(json.dumps(PAGEIDS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (OUT / "publish-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        page.close()
        print("DONE ok", sum(1 for v in results["verified"].values() if v is True), "/", len(results["verified"]))


if __name__ == "__main__":
    main()
