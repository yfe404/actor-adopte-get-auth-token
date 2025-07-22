from __future__ import annotations

import asyncio
from urllib.parse import quote

import httpx
from apify import Actor

PROXY_GROUP = "RESIDENTIAL"
PROXY_COUNTRY = "FR"
API_BASE = "https://api.adopte.app/api/v4"


class RetryTransport(httpx.AsyncBaseTransport):
    def __init__(self, retries=3, backoff=0.5):
        self.retries = retries
        self.backoff = backoff
        self._transport = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        last_exc = None
        for attempt in range(self.retries):
            try:
                response = await self._transport.handle_async_request(request)
                if response.status_code < 500:
                    return response  # only retry on server errors
            except httpx.RequestError as exc:
                last_exc = exc
            await asyncio.sleep(self.backoff * (2**attempt))  # exponential backoff
        if last_exc:
            raise last_exc
        return response  # last response if not successful


async def get_client() -> httpx.AsyncClient:
    proxy_cfg = await Actor.create_proxy_configuration(
        groups=[PROXY_GROUP], country_code=PROXY_COUNTRY
    )

    # ― Obtain proxy components ―
    proxy_info = (
        await proxy_cfg.new_proxy_info()
    )  # gives hostname, port, username, password

    proxy_url = f"http://{quote(proxy_info.username)}:{quote(proxy_info.password)}@{proxy_info.hostname}:{proxy_info.port}"

    timeout = httpx.Timeout(20.0, connect=10.0)
    transport = RetryTransport(retries=5, backoff=1)

    client = httpx.AsyncClient(timeout=timeout, transport=transport, proxy=proxy_url)

    return client


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

        async with await get_client() as client:
            resp = await client.post(
                auth_endpoint, headers=headers, data=payload, follow_redirects=True
            )
            resp.raise_for_status()
            Actor.log.info(f"✅ Status: {resp.status_code}")

            # extract apiRefreshToken from response (html)
            api_refresh_token: str | None = None
            if "apiRefreshToken" in resp.text:
                start_index = resp.text.index("apiRefreshToken") + len(
                    'apiRefreshToken = "'
                )
                end_index = resp.text.index('",', start_index)
                api_refresh_token = resp.text[start_index:end_index]
                Actor.log.info("apiRefreshToken captured from response ✅")
            else:
                Actor.log.error("apiRefreshToken not found in response ❗️")
                # exit with failure
                await Actor.fail("apiRefreshToken not found in response ❗️")
                return

            # ────────────────────────────────────────────────────────────
            # requests → /authtokens & /boost
            # ────────────────────────────────────────────────────────────

            data = {
                "credentials": api_refresh_token,
                "type": "2",
            }

            # Using httpx client instead of requests for consistency
            resp = await client.post(
                "https://api.adopte.app/api/v4/authtokens",
                headers=headers,
                data=data,
            )
            resp.raise_for_status()
            Actor.log.info(f"✅ Status: {resp.status_code}")

            auth_token: str = resp.json()["data"][0]["id"]
            Actor.log.info("Auth token obtained ✅")

            # Push result
            await Actor.push_data(
                {
                    "success": True,
                    "apiRefreshToken": api_refresh_token,
                    "authToken": auth_token,
                    "authtokensStatus": resp.status_code,
                }
            )
            Actor.log.info("Actor finished 🎉")
