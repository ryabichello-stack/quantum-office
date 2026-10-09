#!/usr/bin/env python3
"""Obtain Yandex verification_code for marketing OAuth (Metrika scopes)."""

from __future__ import annotations

import os
import re
import sys
import urllib.parse

from playwright.sync_api import sync_playwright


def main() -> int:
    client_id = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("YANDEX_MARKETING_OAUTH_CLIENT_ID", "")).strip()
    if not client_id:
        print("usage: yandex_marketing_oauth_browser.py <client_id>", file=sys.stderr)
        return 2

    login = os.getenv("YANDEX_LOGIN", "").strip()
    password = os.getenv("YANDEX_PASSWORD", "").strip()
    if not login or not password:
        print("YANDEX_LOGIN and YANDEX_PASSWORD required", file=sys.stderr)
        return 2

    scope = os.getenv("YANDEX_MARKETING_OAUTH_SCOPE", "metrika:read metrika:write").strip()
    redirect = os.getenv(
        "YANDEX_MARKETING_OAUTH_REDIRECT_URI",
        "https://oauth.yandex.ru/verification_code",
    ).strip()
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect,
        "scope": scope,
    }
    url = "https://oauth.yandex.ru/authorize?" + urllib.parse.urlencode(params)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        if page.locator('input[name="login"]').count():
            page.fill('input[name="login"]', login)
            page.locator('button[type="submit"]').first.click()
            page.wait_for_timeout(1500)

        if page.locator('input[name="passwd"]').count():
            page.fill('input[name="passwd"]', password)
            page.locator('button[type="submit"]').first.click()
            page.wait_for_timeout(2500)

        if page.locator('button[data-t="button:action"]').count():
            page.locator('button[data-t="button:action"]').first.click()
            page.wait_for_timeout(2000)

        body = page.content()
        browser.close()

    m = re.search(r"verification_code[^0-9a-zA-Z]*([a-zA-Z0-9]{7,})", body)
    if not m:
        m = re.search(r'class="[^"]*code[^"]*"[^>]*>([a-zA-Z0-9]{7,})<', body)
    if not m:
        print("could not find verification code in OAuth page", file=sys.stderr)
        return 1

    print(m.group(1).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
