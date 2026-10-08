#!/usr/bin/env python3
"""Replace Zero Block footer with CSS footer on all blog T123 blocks via Tilda MCP."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 14431186
URL = "https://tilda.ru/api/mcp/"
PROTO = "2025-11-25"

FOOT_CSS = """
.qp-foot{position:relative;max-width:1200px;margin:0 auto;padding:36px 20px 48px;box-sizing:border-box;overflow:hidden;color:#fff}
.qp-foot a{color:#fff!important;text-decoration:none!important}
.qp-foot a:hover{color:#ff6400!important;text-decoration:none!important}
.qp-foot__bg{position:absolute;right:-40px;top:0;width:432px;height:100%;background:url(https://static.tildacdn.com/tild3364-6365-4866-a332-646463616233/photo.png) right center/cover no-repeat;opacity:.95;pointer-events:none;border-radius:50px;z-index:0}
.qp-foot__inner{position:relative;z-index:1;display:grid;grid-template-columns:362px 1fr 1fr;gap:28px;align-items:start}
.qp-foot__card{background:#282828;border:1px solid #3a3a3a;border-radius:25px;padding:28px 24px 16px;min-height:383px;box-sizing:border-box;display:flex;flex-direction:column}
.qp-foot__title{margin:0 0 14px;font-size:25px;font-weight:300;line-height:1.15;color:#fff}
.qp-foot__title strong{font-weight:600}
.qp-foot__lead{margin:0 0 22px;font-size:17px;font-weight:300;line-height:1.2;color:#fff}
.qp-foot__cta{display:inline-flex;align-items:center;justify-content:center;align-self:flex-start;min-width:189px;height:35px;padding:0 16px;border:1px solid #ff6400;border-radius:12px;background:#ff6400;color:#fff!important;font-size:14px;font-weight:400;letter-spacing:.5px;text-transform:uppercase;text-decoration:none!important;box-sizing:border-box}
.qp-foot__cta:hover{background:#282828;color:#fff!important;text-decoration:none!important}
.qp-foot__coins{display:block;width:230px;max-width:100%;height:auto;margin:18px 0 0 auto}
.qp-foot__label{margin:0 0 10px;font-size:17px;font-weight:100;line-height:1.55;color:#fff}
.qp-foot__label--menu{margin-top:28px}
.qp-foot__phone,.qp-foot__mail{display:block;font-size:17px;font-weight:400;line-height:1.55;color:#fff!important;text-decoration:none!important}
.qp-foot__mail{margin-bottom:4px}
.qp-foot__menu,.qp-foot__legal{list-style:none;margin:0;padding:0}
.qp-foot__menu li{margin:0 0 10px}
.qp-foot__menu a{font-size:15px;font-weight:300;line-height:1.55;color:#fff!important;text-decoration:none!important}
.qp-foot__menu a:hover{color:#ff6400!important}
.qp-foot__soc{display:flex;gap:10px;margin:0 0 18px}
.qp-foot__soc a{display:block;width:52px;height:52px;border-radius:14px;background-color:#282828;background-position:center;background-repeat:no-repeat;background-size:28px 28px;text-decoration:none!important}
.qp-foot__soc a.i-web{background-image:url(https://static.tildacdn.com/tild6433-3339-4139-b231-343265366339/noroot.png)}
.qp-foot__soc a.i-tg{background-image:url(https://static.tildacdn.com/tild6263-3535-4536-b130-663735313033/noroot.png)}
.qp-foot__soc a.i-wa{background-image:url(https://static.tildacdn.com/tild3363-3262-4538-b833-643564376561/noroot.png);background-size:30px 30px}
.qp-foot__legal li{margin:0 0 8px}
.qp-foot__legal a{font-size:15px;font-weight:400;line-height:1.55;color:#fff!important;text-decoration:none!important}
.qp-foot__legal a:hover{color:#ff6400!important}
.qp-foot__copy{margin:14px 0 12px;font-size:15px;font-weight:300;line-height:1.55;color:#fff}
.qp-foot__logo{display:inline-block;width:120px;text-decoration:none!important}
.qp-foot__logo img{display:block;width:120px;height:auto}
@media(max-width:980px){
.qp-foot__inner{grid-template-columns:1fr 1fr;gap:20px}
.qp-foot__card{grid-column:1/-1;min-height:0}
.qp-foot__bg{opacity:.35}
}
@media(max-width:720px){
.qp-foot__inner{grid-template-columns:1fr}
.qp-foot__bg{display:none}
.qp-foot__coins{margin-left:0;margin-right:auto}
}
""".strip()

FOOT_HTML = (ROOT / "html" / "_footer_main.html").read_text(encoding="utf-8").strip()

session = None


def get_key() -> str:
    k = os.environ.get("TILDA_MCP_KEY", "").strip()
    if k.startswith("mcp_tilda_"):
        return k
    m = re.search(r"(mcp_tilda_[A-Za-z0-9]+)", (ROOT.parents[2] / ".cursor" / "mcp.json").read_text())
    if not m:
        raise SystemExit("TILDA_MCP_KEY missing")
    return m.group(1)


def _post(body: dict):
    global session
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {get_key()}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTO,
        "Connection": "close",
    }
    if session:
        headers["Mcp-Session-Id"] = session
    req = urllib.request.Request(URL, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        raw = r.read().decode("utf-8", "ignore")
        sess = r.headers.get("Mcp-Session-Id") or r.headers.get("mcp-session-id")
        if sess:
            session = sess
        return r.status, raw


def call(method: str, params=None, note: bool = False, retries: int = 6):
    global session
    body: dict = {"jsonrpc": "2.0", "method": method}
    if not note:
        body["id"] = 1
    if params is not None:
        body["params"] = params
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            return _post(body)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "ignore")
        except Exception as e:
            last_err = e
            session = None
            time.sleep(2 * (attempt + 1))
            if attempt < retries - 1:
                try:
                    _post(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": PROTO,
                                "capabilities": {},
                                "clientInfo": {"name": "fix-footer", "version": "1"},
                            },
                        }
                    )
                    _post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
                except Exception:
                    pass
    raise RuntimeError(f"MCP call failed after retries: {last_err}")


def parse(raw: str):
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    out = None
    for line in raw.splitlines():
        if line.startswith("data:") and line[5:].strip():
            out = json.loads(line[5:].strip())
    return out


def tool(name: str, arguments=None):
    st, raw = call("tools/call", {"name": name, "arguments": arguments or {}})
    msg = parse(raw)
    if not msg or "error" in msg:
        raise RuntimeError(f"{name}: {(msg or {}).get('error') or raw[:800]}")
    res = msg["result"]
    if isinstance(res, dict) and "content" in res:
        texts = [c.get("text", "") for c in res["content"] if c.get("type") == "text"]
        joined = "\n".join(texts)
        try:
            return json.loads(joined)
        except Exception:
            return joined
    return res


def init():
    call(
        "initialize",
        {
            "protocolVersion": PROTO,
            "capabilities": {},
            "clientInfo": {"name": "fix-footer", "version": "1"},
        },
    )
    call("notifications/initialized", {}, note=True)


ZERO_RE = re.compile(
    r"(?:<!--\s*QP main-site footer[\s\S]*?-->\s*)?"
    r"(?:<script\b[^>]*tilda-zero[\s\S]*?</script>\s*)+"
    r'<div id="rec1275972401"[\s\S]*?<!--\s*/T396\s*-->\s*</div>\s*',
    re.I,
)

HOME_CSS_LINK_RE = re.compile(
    r'<link\s+rel="stylesheet"\s+href="https://static\.tildacdn\.com/ws/project14431186/tilda-blocks-page75572866[^"]*"\s*/?>\s*',
    re.I,
)


def transform(code: str) -> str:
    code = HOME_CSS_LINK_RE.sub("", code)
    if "qp-foot__cta" not in code:
        if "</style>" not in code:
            raise RuntimeError("no </style> to inject footer CSS")
        code = code.replace("</style>", FOOT_CSS + "\n</style>", 1)
    if ZERO_RE.search(code):
        code = ZERO_RE.sub(FOOT_HTML + "\n", code, count=1)
    elif 'id="rec1275972401"' in code:
        raise RuntimeError("found rec1275972401 but regex did not match")
    elif "qp-foot__menu" in code and 'id="rec1275972401"' in code:
        pass  # already CSS
    elif "qp-foot__cta" in code and "tilda-zero" not in code:
        pass  # already CSS
    else:
        # insert before JSON-LD or before final close
        m = re.search(r'<script\s+type="application/ld\+json">', code)
        if m:
            code = code[: m.start()] + FOOT_HTML + "\n" + code[m.start() :]
        else:
            # before last </div> of qp-blog — append before end
            idx = code.rfind("</div>")
            if idx < 0:
                raise RuntimeError("cannot find insertion point for footer")
            code = code[:idx] + FOOT_HTML + "\n" + code[idx:]
    # strip leftover zero scripts if any
    code = re.sub(
        r'<script\b[^>]*tilda-zero[\s\S]*?</script>\s*',
        "",
        code,
        flags=re.I,
    )
    return code


def main():
    init()
    pages = tool("get_pages", {"projectid": PROJECT})
    if isinstance(pages, str):
        pages = json.loads(pages)
    blog = [p for p in pages if str(p.get("alias", "")).startswith("blog")]
    blog = sorted(blog, key=lambda p: p["alias"])
    report = []
    for p in blog:
        pageid = int(p["id"])
        alias = p["alias"]
        time.sleep(0.3)
        records = tool("get_page_records", {"pageid": pageid, "projectid": PROJECT})
        if isinstance(records, str):
            records = json.loads(records)
        html_rec = None
        t966 = None
        for r in records if isinstance(records, list) else []:
            tpl = int(r.get("tplid") or r.get("typeid") or 0)
            rid_raw = r.get("id") or r.get("recordid") or r.get("recid")
            if rid_raw is None:
                continue
            rid = int(rid_raw)
            if tpl == 131:
                html_rec = rid
            if tpl == 966:
                t966 = rid
        if not html_rec:
            report.append(
                {
                    "alias": alias,
                    "ok": False,
                    "error": "no T123",
                    "records_sample": (records[:2] if isinstance(records, list) else records),
                }
            )
            print("FAIL", alias, "no T123", records[:1] if isinstance(records, list) else records)
            continue
        time.sleep(0.3)
        ed = tool(
            "edit_record",
            {
                "pageid": pageid,
                "recordid": html_rec,
                "projectid": PROJECT,
                "tab": "content",
            },
        )
        old = ed["record"]["code"]
        already = (
            "qp-foot__cta" in old
            and "tilda-zero" not in old
            and "t396__artboard" not in old
            and 'id="rec1275972401"' in old
        )
        if already:
            report.append(
                {
                    "alias": alias,
                    "ok": True,
                    "status": "already_css",
                    "pageid": pageid,
                    "recid": html_rec,
                    "t966": t966,
                    "old_len": len(old),
                    "new_len": len(old),
                }
            )
            print("SKIP", alias, "already_css")
            continue
        try:
            new = transform(old)
        except Exception as e:
            report.append({"alias": alias, "ok": False, "error": str(e), "pageid": pageid, "recid": html_rec})
            print("FAIL", alias, e)
            continue
        if new == old:
            status = "unchanged"
        else:
            time.sleep(0.6)
            tool(
                "update_record",
                {
                    "pageid": pageid,
                    "recordid": html_rec,
                    "projectid": PROJECT,
                    "tab": "content",
                    "only_field": "code",
                    "fields": {"code": new},
                },
            )
            status = "updated"
        # sanity
        ok = (
            "qp-foot__cta" in new
            and "tilda-zero" not in new
            and 'id="rec1275972401"' in new
            and "t396__artboard" not in new
        )
        report.append(
            {
                "alias": alias,
                "ok": ok,
                "status": status,
                "pageid": pageid,
                "recid": html_rec,
                "t966": t966,
                "old_len": len(old),
                "new_len": len(new),
            }
        )
        print(("OK" if ok else "BAD"), alias, status, f"{len(old)}→{len(new)}")
        time.sleep(0.4)

    out = ROOT / "scripts" / "_footer_fix_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("report", out)
    bad = [r for r in report if not r.get("ok")]
    if bad:
        raise SystemExit(f"{len(bad)} failures")


if __name__ == "__main__":
    main()
