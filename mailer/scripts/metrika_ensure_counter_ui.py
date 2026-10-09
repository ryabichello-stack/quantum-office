#!/usr/bin/env python3
"""Find or create a Yandex Metrika counter for a site via metrika.yandex.ru UI."""

from __future__ import annotations

import os
import re
import sys

from playwright.sync_api import sync_playwright


def _dismiss_cookies(page) -> None:
    for label in ("Allow all", "Разрешить все", "Allow essential cookies"):
        loc = page.locator(f'button:has-text("{label}")')
        if loc.count():
            loc.first.click(force=True)
            page.wait_for_timeout(900)


def _yandex_login(page, login: str, password: str) -> None:
    page.goto("https://passport.yandex.ru/auth/list?retpath=https://metrika.yandex.ru/", timeout=60000)
    _dismiss_cookies(page)
    for label in ("Other login method", "Другой способ войти", "More", "Ещё"):
        loc = page.locator(f'button:has-text("{label}")')
        if loc.count():
            loc.first.click(force=True)
            page.wait_for_timeout(1000)
    if page.locator('input[name="login"]').count():
        page.fill('input[name="login"]', login)
        page.locator('button[type="submit"]').first.click(force=True)
        page.wait_for_timeout(1500)
    if page.locator('input[name="passwd"]').count():
        page.fill('input[name="passwd"]', password)
        page.locator('button[type="submit"]').first.click(force=True)
        page.wait_for_timeout(3000)
    _dismiss_cookies(page)


def main() -> int:
    site = (sys.argv[1] if len(sys.argv) > 1 else "dlno.ru").strip().lower()
    login = os.getenv("YANDEX_LOGIN", "").strip()
    password = os.getenv("YANDEX_PASSWORD", "").strip()
    if not login or not password:
        print("YANDEX_LOGIN and YANDEX_PASSWORD required", file=sys.stderr)
        return 2

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        _yandex_login(page, login, password)
        page.goto("https://metrika.yandex.ru/list", timeout=60000)
        page.wait_for_timeout(4000)
        if "passport.yandex" in page.url:
            print(f"login_failed url={page.url}", file=sys.stderr)
            browser.close()
            return 1
        html = page.content()
        text = page.inner_text("body")

        # Existing counter links: /dashboard?id=12345678
        ids = set(re.findall(r"/dashboard\?id=(\d+)", html))
        if ids:
            browser.close()
            print(sorted(ids)[-1])
            return 0

        if site in text.lower() or "dlno" in text.lower():
            m = re.search(r"(\d{6,12})", text)
            if m:
                browser.close()
                print(m.group(1))
                return 0

        # Create counter
        add = page.locator('a:has-text("Add counter"), button:has-text("Add counter"), a:has-text("Добавить счётчик"), button:has-text("Добавить счётчик")')
        if add.count():
            add.first.click(force=True)
            page.wait_for_timeout(2000)
        if page.locator('input[name="site"]').count():
            page.fill('input[name="site"]', site)
        elif page.locator('input[placeholder*="site"], input[placeholder*="сайт"]').count():
            page.locator('input[placeholder*="site"], input[placeholder*="сайт"]').first.fill(site)
        name_input = page.locator('input[name="name"]')
        if name_input.count():
            name_input.fill(f"DELNO {site}")
        submit = page.locator('button[type="submit"], button:has-text("Create"), button:has-text("Создать")')
        if submit.count():
            submit.first.click(force=True)
            page.wait_for_timeout(5000)

        page.wait_for_timeout(3000)
        url = page.url
        html = page.content()
        browser.close()

    m = re.search(r"id=(\d+)", url)
    if m:
        print(m.group(1))
        return 0
    ids = re.findall(r"/dashboard\?id=(\d+)", html)
    if ids:
        print(ids[-1])
        return 0

    print("could not resolve Metrika counter id", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
