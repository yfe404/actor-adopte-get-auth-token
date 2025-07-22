from __future__ import annotations

from urllib.parse import quote

import requests
from apify import Actor

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
        if not email or not password:
            await Actor.fail("Input must contain email and password ❗️")
            return

        # Proxy (shared)
        requests_proxies, _ = await get_proxy()

        auth_endpoint = "https://www.adopte.app/auth/login"
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Platform": "web",
        }
        payload = {
            "username": email,
            "password": password,
            "remember": "true",
        }
        resp = requests.post(
            auth_endpoint,
            headers=headers,
            data=payload,
            proxies=requests_proxies,
            timeout=60,
        )
        resp.raise_for_status()
        Actor.log.info(f"✅ Status: {resp.status_code}")
        # print("🔐 Login response:", resp.text)

        # extract apiRefreshToken from response (html)
        api_refresh_token: str | None = None
        if "apiRefreshToken" in resp.text:
            # If the response contains the token, extract it
            start_index = resp.text.index("apiRefreshToken") + len(
                'apiRefreshToken = "'
            )
            end_index = resp.text.index('",', start_index)
            api_refresh_token = resp.text[start_index:end_index]
            Actor.log.info("apiRefreshToken captured from response ✅")
        else:
            Actor.error("apiRefreshToken not found in response ❗️")
            # exit with failure
            await Actor.fail("apiRefreshToken not found in response ❗️")

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
        Actor.log.info(f"✅ Status: {resp.status_code}")

        auth_token: str = resp.json()["data"][0]["id"]
        Actor.log.info("Auth token obtained ✅")

        headers["Authorization"] = f"Bearer {auth_token}"
        # GET /boost
        boost_url = "https://api.adopte.app/api/v4/boost"
        boost_resp = requests.get(
            boost_url,
            headers=headers,
            proxies=requests_proxies,
            timeout=300,
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
