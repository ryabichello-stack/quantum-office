#!/usr/bin/env python3
"""Upload blog T123 HTML via Tilda MCP in small UTF-8 chunks (server drops ~6KB posts)."""
from __future__ import annotations

import json
import os
import re
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 14431186
URL = "https://tilda.ru/api/mcp/"
PROTO = "2025-11-25"
MAX_CODE = 3000  # cyrillic-heavy; wire limit ~5.7KB

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
@media(max-width:980px){.qp-foot__inner{grid-template-columns:1fr 1fr;gap:20px}.qp-foot__card{grid-column:1/-1;min-height:0}.qp-foot__bg{opacity:.35}}
@media(max-width:720px){.qp-foot__inner{grid-template-columns:1fr}.qp-foot__bg{display:none}.qp-foot__coins{margin-left:0;margin-right:auto}}
""".strip()

FOOT_HTML = re.sub(
    r"\s+",
    " ",
    re.sub(r"<!--.*?-->", "", (ROOT / "html" / "_footer_main.html").read_text(encoding="utf-8"), flags=re.S),
).strip()
FOOT_HTML = re.sub(r">\s+<", "><", FOOT_HTML)

session = None


def get_key() -> str:
    k = os.environ.get("TILDA_MCP_KEY", "").strip()
    if not k.startswith("mcp_tilda_"):
        raise SystemExit("TILDA_MCP_KEY missing")
    return k


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
    with urllib.request.urlopen(req, timeout=120) as r:
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
    last = None
    for attempt in range(retries):
        try:
            return _post(body)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "ignore")
            if e.code in (429, 502, 503) and attempt < retries - 1:
                time.sleep(2.5 * (attempt + 1))
                session = None
                continue
            return e.code, raw
        except Exception as e:
            last = e
            session = None
            time.sleep(1.5 * (attempt + 1))
            try:
                _post(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": PROTO,
                            "capabilities": {},
                            "clientInfo": {"name": "chunk-upload", "version": "1"},
                        },
                    }
                )
                _post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
            except Exception:
                pass
    raise RuntimeError(last)


def parse(raw: str):
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    out = None
    for line in raw.splitlines():
        if line.startswith("data:") and line[5:].strip():
            out = json.loads(line[5:].strip())
    return out


def _is_rate_limited(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    if obj.get("error_code") == "rate_limited":
        return True
    if obj.get("code") == -32033:
        return True
    data = obj.get("data")
    if isinstance(data, dict) and data.get("error_code") == "rate_limited":
        return True
    msg = str(obj.get("message", "")).lower()
    return "rate limit" in msg


def tool(name: str, arguments=None, retries: int = 8):
    global session
    last_err = None
    for attempt in range(retries):
        st, raw = call("tools/call", {"name": name, "arguments": arguments or {}})
        msg = parse(raw)
        if not msg:
            last_err = RuntimeError(f"{name}: empty response status={st}")
            time.sleep(2 * (attempt + 1))
            session = None
            continue
        if "error" in msg:
            err = msg["error"]
            if _is_rate_limited(err) and attempt < retries - 1:
                wait = 8 + 4 * attempt
                data = err.get("data") if isinstance(err, dict) else None
                if isinstance(data, dict) and data.get("retry_at"):
                    wait = max(wait, int(data["retry_at"]) - int(time.time()) + 1)
                wait = min(max(wait, 3), 90)
                print(f"    rate-limit {name}, sleep {wait}s", flush=True)
                time.sleep(wait)
                session = None
                init()
                continue
            raise RuntimeError(f"{name}: {err}")
        res = msg.get("result")
        if isinstance(res, dict) and res.get("isError"):
            texts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
            joined = "\n".join(texts)
            try:
                parsed = json.loads(joined)
            except Exception:
                parsed = None
            if _is_rate_limited(parsed) and attempt < retries - 1:
                wait = 8 + 4 * attempt
                print(f"    rate-limit(result) {name}, sleep {wait}s", flush=True)
                time.sleep(wait)
                session = None
                init()
                continue
            raise RuntimeError(f"{name} isError: {joined[:400]}")
        if isinstance(res, dict) and "content" in res:
            texts = [c.get("text", "") for c in res["content"] if c.get("type") == "text"]
            joined = "\n".join(texts)
            try:
                return json.loads(joined)
            except Exception:
                return joined
        return res
    raise RuntimeError(last_err or f"{name}: retries exhausted")


def init():
    print("init", flush=True)
    call(
        "initialize",
        {
            "protocolVersion": PROTO,
            "capabilities": {},
            "clientInfo": {"name": "chunk-upload", "version": "1"},
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


def minify_css(css: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,])\s*", r"\1", css)
    return css.strip()


def _css_top_level_rules(css: str) -> list[str]:
    """Split CSS into top-level rules only (keeps @media blocks intact)."""
    rules: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in css:
        buf.append(ch)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                rules.append("".join(buf).strip())
                buf = []
            elif depth < 0:
                raise RuntimeError("css brace underflow")
    tail = "".join(buf).strip()
    if tail:
        rules.append(tail)
    return [r for r in rules if r]


def style_chunks(css: str, max_inner: int = 2800) -> list[str]:
    css = minify_css(css)
    parts: list[str] = []
    buf = ""
    for rule in _css_top_level_rules(css):
        if len(rule) > max_inner:
            raise RuntimeError(f"css rule too long: {len(rule)}")
        if buf and len(buf) + len(rule) > max_inner:
            parts.append(f"<style>{buf}</style>")
            buf = rule
        else:
            buf += rule
    if buf:
        parts.append(f"<style>{buf}</style>")
    # sanity: no chunk may start with a stray closing brace
    for i, p in enumerate(parts):
        inner = p[len("<style>") : -len("</style>")]
        if inner.startswith("}"):
            raise RuntimeError(f"style chunk {i} starts with stray }}")
        if inner.count("{") != inner.count("}"):
            raise RuntimeError(f"style chunk {i} unbalanced braces")
    return parts


def _extract_footer(body: str) -> tuple[str, str]:
    """Return (body_without_footer, footer_html). Footer must stay atomic across T123."""
    m = re.search(
        r"(?:<!--\s*Blog footer[\s\S]*?-->\s*)?<footer\b[^>]*\bqp-foot\b[\s\S]*?</footer>\s*",
        body,
        re.I,
    )
    if m:
        return (body[: m.start()] + body[m.end() :]).strip(), m.group(0).strip()
    m = re.search(
        r'<footer\b[^>]*id="rec1275972401"[\s\S]*?</footer>\s*',
        body,
        re.I,
    )
    if m:
        return (body[: m.start()] + body[m.end() :]).strip(), m.group(0).strip()
    # fallback: inject canonical footer
    return body.strip(), FOOT_HTML


def split_body(html: str, max_len: int = MAX_CODE) -> list[str]:
    """Split pre-footer body into self-contained sibling chunks; footer is last & atomic."""
    main, footer = _extract_footer(html)
    if len(footer) > max_len:
        raise RuntimeError(f"footer too long for one T123: {len(footer)}")

    # Prefer cutting after complete top-level blocks inside .qp-blog / .qp-wrap
    parts: list[str] = []
    while main:
        if len(main) <= max_len:
            parts.append(main)
            break
        window = main[:max_len]
        cut = -1
        # Never cut on generic </div> — that splits nested trees across T123 wrappers.
        for marker in (
            "</section>",
            "</article>",
            "</table>",
            "</ul>",
            "</ol>",
            "</h2>",
            "</h3>",
            "</p>",
            "<!-- /qp-section -->",
            "\n\n",
        ):
            pos = window.rfind(marker)
            if pos > max_len * 0.35:
                cut = max(cut, pos + len(marker))
        if cut < 0:
            # last resort: cut after a complete card/link sibling
            for marker in ('</a>\n', "</a> ", "</a>"):
                pos = window.rfind(marker)
                if pos > max_len * 0.5:
                    cut = max(cut, pos + len(marker))
                    break
        if cut < 0:
            raise RuntimeError(
                f"cannot split body safely at len={len(main)}; "
                "add markers or raise MAX_CODE"
            )
        parts.append(main[:cut])
        main = main[cut:].lstrip()

    parts.append(footer)
    for i, p in enumerate(parts):
        if len(p) > max_len:
            raise RuntimeError(f"body chunk {i} too long: {len(p)}")
        if i < len(parts) - 1 and ("<footer" in p or "qp-foot__cta" in p):
            raise RuntimeError(f"footer leaked into body chunk {i}")
    if "<footer" not in parts[-1] or "</footer>" not in parts[-1]:
        raise RuntimeError("footer chunk incomplete")
    return parts


def build_chunks_from_full_html(code: str) -> list[str]:
    code = HOME_CSS_LINK_RE.sub("", code)
    if ZERO_RE.search(code):
        code = ZERO_RE.sub(FOOT_HTML + "\n", code, count=1)
    code = re.sub(r"<script\b[^>]*tilda-zero[\s\S]*?</script>\s*", "", code, flags=re.I)
    if "t396__artboard" in code:
        raise RuntimeError("zero artboard still present")

    styles = re.findall(r"<style>([\s\S]*?)</style>", code)
    if not styles:
        raise RuntimeError("no style block")
    css = "\n".join(styles)
    if "qp-foot__cta" not in css:
        css += "\n" + FOOT_CSS
    body = re.sub(r"<style>[\s\S]*?</style>\s*", "", code, count=len(styles))
    body = body.strip()
    # Always use canonical FOOT_HTML so chunking sees one clean footer block
    body_wo, _old = _extract_footer(body)
    body = (body_wo + "\n" + FOOT_HTML).strip()

    chunks: list[str] = []
    chunks.extend(style_chunks(css))
    chunks.extend(split_body(body))
    for i, c in enumerate(chunks):
        if len(c) > MAX_CODE:
            raise RuntimeError(f"chunk {i} len {len(c)} > {MAX_CODE}")
    # final invariant: exactly one complete footer across all chunks
    foot_chunks = [c for c in chunks if "<footer" in c]
    if len(foot_chunks) != 1 or "</footer>" not in foot_chunks[0]:
        raise RuntimeError("footer must be exactly one complete chunk")
    return chunks


def set_code(pageid: int, recordid: int, code: str):
    if len(code) > MAX_CODE:
        raise RuntimeError(f"too long {len(code)}")
    return tool(
        "update_record",
        {
            "pageid": pageid,
            "recordid": recordid,
            "projectid": PROJECT,
            "tab": "content",
            "only_field": "code",
            "fields": {"code": code},
        },
    )


def add_html_block(pageid: int, afterid: int) -> int:
    res = tool(
        "add_record",
        {"pageid": pageid, "projectid": PROJECT, "tplid": 131, "afterid": afterid},
    )
    text = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
    if isinstance(res, dict):
        for k in ("recordid", "id"):
            if res.get(k):
                return int(res[k])
        rec = res.get("record")
        if isinstance(rec, dict) and rec.get("id"):
            return int(rec["id"])
    m = re.search(r"(\d{9,})", text)
    if not m:
        raise RuntimeError(f"bad add_record: {res!r}")
    return int(m.group(1))


def html_records(pageid: int) -> list[int]:
    records = tool("get_page_records", {"pageid": pageid, "projectid": PROJECT})
    if isinstance(records, str):
        records = json.loads(records)
    ids = []
    for r in records if isinstance(records, list) else []:
        if int(r.get("tplid") or 0) == 131:
            rid = r.get("recordid") or r.get("id")
            if rid:
                ids.append(int(rid))
    return ids


def upload(pageid: int, source_html: str):
    chunks = build_chunks_from_full_html(source_html)
    print(f"  chunks={len(chunks)} {[len(c) for c in chunks]}", flush=True)
    ids = html_records(pageid)
    if not ids:
        raise RuntimeError("no html record")
    primary = ids[0]
    extras = ids[1:]
    set_code(pageid, primary, chunks[0])
    time.sleep(0.55)
    prev = primary
    used = [primary]
    for chunk in chunks[1:]:
        if extras:
            rid = extras.pop(0)
        else:
            rid = add_html_block(pageid, afterid=prev)
            time.sleep(0.65)
        set_code(pageid, rid, chunk)
        time.sleep(0.55)
        used.append(rid)
        prev = rid
    for rid in extras:
        set_code(pageid, rid, "<!-- cleared -->")
        time.sleep(0.35)
    return used


def load_source(alias: str) -> str:
    """Prefer local pack HTML (already CSS footer). gph may use /tmp restore."""
    if alias == "blog-gph" and Path("/tmp/gph_new.html").exists():
        print("  source=/tmp/gph_new.html", flush=True)
        return Path("/tmp/gph_new.html").read_text(encoding="utf-8")
    for path in (
        ROOT / "CODEX_TILDA_PACK" / "html" / f"{alias}.html",
        ROOT / "html" / f"{alias}.html",
    ):
        if path.exists():
            print(f"  source={path.relative_to(ROOT)}", flush=True)
            return path.read_text(encoding="utf-8")
    raise RuntimeError(f"no local html for {alias}")


def main():
    init()
    pages = tool("get_pages", {"projectid": PROJECT})
    if isinstance(pages, str):
        pages = json.loads(pages)
    blog = sorted(
        [p for p in pages if str(p.get("alias", "")).startswith("blog")],
        key=lambda p: p["alias"],
    )
    report = []
    for p in blog:
        alias = p["alias"]
        pageid = int(p["id"])
        print("==", alias, pageid, flush=True)
        try:
            ids = html_records(pageid)
            if not ids:
                raise RuntimeError("no T123")
            src = load_source(alias)
            used = upload(pageid, src)
            pub = tool("publish_page", {"pageid": pageid, "projectid": PROJECT})
            report.append(
                {
                    "alias": alias,
                    "ok": True,
                    "recordids": used,
                    "publish": pub,
                    "pageid": pageid,
                }
            )
            print("  OK published", flush=True)
        except Exception as e:
            report.append(
                {
                    "alias": alias,
                    "ok": False,
                    "error": f"{type(e).__name__}: {e}",
                    "pageid": pageid,
                    "trace": traceback.format_exc(),
                }
            )
            print("  FAIL", type(e).__name__, e, flush=True)
        time.sleep(0.8)
    out = ROOT / "scripts" / "_chunk_upload_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("report", out, "ok", sum(1 for r in report if r.get("ok")), "/", len(report), flush=True)
    if any(not r.get("ok") for r in report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
