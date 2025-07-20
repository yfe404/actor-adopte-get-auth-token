"""Apify Actor entry point: Adopte.app login + token extraction.

• Uses Apify FR residential proxy (one single config shared by Playwright *and* requests).
• Login done in Playwright → grabs `window.apiRefreshToken`.
• `/authtokens` + `/boost` contacted via **requests** through the *same* proxy.
• Built‑in retries + clear error messages if proxy tunnel cannot be established.
"""

from __future__ import annotations

import asyncio

import requests
from apify import Actor
from playwright.async_api import async_playwright

PROXY_GROUP = "RESIDENTIAL"
PROXY_COUNTRY = "FR"
API_BASE = "https://api.adopte.app/api/v4"


async def get_proxy() -> tuple[dict[str, str], dict]:
    """Create ONE proxy configuration and return (requests_proxies, playwright_proxy_dict)."""
    proxy_cfg = await Actor.create_proxy_configuration(
        groups=[PROXY_GROUP], country_code=PROXY_COUNTRY
    )

    # ― Obtain proxy components ―
    proxy_info = (
        await proxy_cfg.new_proxy_info()
    )  # gives hostname, port, username, password

    from urllib.parse import quote

    proxy_url = f"http://{quote(proxy_info.username)}:{quote(proxy_info.password)}@{proxy_info.hostname}:{proxy_info.port}"
    # requests uses single URL; Playwright needs split creds
    requests_proxies = {"http": proxy_url, "https": proxy_url}
    playwright_proxy = {
        "server": f"http://{proxy_info.hostname}:{proxy_info.port}",
        "username": proxy_info.username,
        "password": proxy_info.password,
    }
    return requests_proxies, playwright_proxy


async def main() -> None:
    async with Actor:
        # ────────────────────────────────────────────────────────────
        # Input
        # ────────────────────────────────────────────────────────────
        inp = await Actor.get_input() or {}
        email: str | None = inp.get("email")
        password: str | None = inp.get("password")
        headless: bool = inp.get("headless", True)
        if not email or not password:
            await Actor.fail("Input must contain email and password ❗️")
            return

        # Proxy (shared)
        requests_proxies, playwright_proxy = await get_proxy()

        # ────────────────────────────────────────────────────────────
        # Playwright → fetch refresh token
        # ────────────────────────────────────────────────────────────
        api_refresh_token: str | None = None
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=["--disable-gpu"],
                proxy=playwright_proxy,
            )
            context = await browser.new_context()
            # Give all navigations up to 60 s – the residential proxy can be slow
            context.set_default_navigation_timeout(60_000)
            page = await context.new_page()

            try:
                await page.goto(
                    "https://www.adopte.app",
                    wait_until="load",
                    timeout=60_000,
                )
            except Exception as e:
                await Actor.fail(f"Navigation to adopte.app failed: {e}")
                return

            # Wait for the login button to become visible
            await page.wait_for_selector("#btn-display-login", timeout=20_000)
            await page.click("#btn-display-login")
            await page.fill("#mail", email)
            await page.fill("#password", password)
            await page.press("#password", "Enter")
            Actor.log.info("Submitted login form – waiting for refresh‑token …")
            await page.wait_for_function("window.apiRefreshToken", timeout=45_000)
            api_refresh_token: str = await page.evaluate("window.apiRefreshToken")
            Actor.log.info("apiRefreshToken captured ✅")

        # ────────────────────────────────────────────────────────────
        # requests → /authtokens & /boost
        # ────────────────────────────────────────────────────────────

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Platform": "web",
        }

        data = {
            "credentials": api_refresh_token,
            "type": "2",
        }
        resp = requests.post(
            "https://api.adopte.app/api/v4/authtokens",
            headers=headers,
            data=data,
            proxies=requests_proxies,
            timeout=10,
        )
        resp.raise_for_status()
        print("✅ Status:", resp.status_code)
        print("🔐 Token response:", resp.text)

        auth_token: str = resp.json()["data"][0]["id"]
        Actor.log.info("Auth token obtained ✅")

        headers["Authorization"] = f"Bearer {auth_token}"
        # GET /boost
        boost_url = "https://api.adopte.app/api/v4/boost"
        boost_resp = requests.get(
            boost_url,
            headers=headers,
            proxies=requests_proxies,
            timeout=10,
        )
        Actor.log.info(f"/boost status {boost_resp.status_code}")

        # Push result
        await Actor.push_data(
            {
                "success": True,
                "apiRefreshToken": api_refresh_token,
                "authToken": auth_token,
                "authtokensStatus": resp.status_code,
                "boostStatus": boost_resp.status_code,
                "boostBody": boost_resp.text,
            }
        )
        Actor.log.info("Actor finished 🎉")


if __name__ == "__main__":
    asyncio.run(main())
