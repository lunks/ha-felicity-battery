"""DataUpdateCoordinator for Felicity Battery."""

from __future__ import annotations

import logging
import re
import ssl
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import async_login
from .const import (
    API_BASE_URL,
    API_HEADERS,
    DOMAIN,
    ENDPOINT_DEVICE_LIST,
    ENDPOINT_DEVICE_SNAPSHOT,
)
from .ssl_context import get_ssl_context

_LOGGER = logging.getLogger(__name__)


class FelicityBatteryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to poll the Felicity Solar API."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        username: str,
        password: str,
        device_sn: str,
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.username = username
        self.password = password
        self.device_sn = device_sn
        self.token: str | None = None
        self.device_model: str | None = None
        self.device_alias: str | None = None
        self.device_timezone: timedelta = timedelta(hours=0)
        self._session = async_get_clientsession(hass)
        self._ssl: ssl.SSLContext | None = None

    async def _get_ssl(self) -> ssl.SSLContext:
        """Build the SSL context off the event loop (blocking cert load)."""
        if self._ssl is None:
            self._ssl = await self.hass.async_add_executor_job(get_ssl_context)
        return self._ssl

    def _headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = dict(API_HEADERS)
        if self.token:
            headers["Authorization"] = self.token
        return headers

    async def _ensure_token(self) -> None:
        """Login to get a fresh token if we don't have one."""
        if self.token:
            return
        await self._login()

    async def _post(self, url: str, payload: dict) -> aiohttp.ClientResponse:
        """POST with bundled SSL context and auth headers."""
        return await self._session.post(
            url, json=payload, headers=self._headers(), ssl=await self._get_ssl()
        )

    async def _login(self) -> None:
        """Authenticate and store the JWT token."""
        try:
            self.token = await async_login(
                self._session,
                self.username,
                self.password,
                ssl_ctx=await self._get_ssl(),
            )
        except ValueError as err:
            raise ConfigEntryAuthFailed(f"Login failed: {err}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error during login: {err}") from err

    def _is_auth_error(self, resp_status: int, data: dict | None = None) -> bool:
        """Check if the response indicates an authentication failure."""
        if resp_status in (401, 302):
            return True
        if data and data.get("code") == 401:
            return True
        return False

    @staticmethod
    def _parse_utc_offset(tz_str: str) -> timedelta:
        """Parse 'UTC-03:00' or 'UTC+05:30' to a timedelta."""
        match = re.match(r"UTC([+-])(\d{2}):(\d{2})", tz_str or "")
        if not match:
            return timedelta(hours=0)
        sign = 1 if match.group(1) == "+" else -1
        return timedelta(
            hours=sign * int(match.group(2)), minutes=sign * int(match.group(3))
        )

    async def fetch_device_info(self) -> None:
        """Fetch device model and timezone info."""
        await self._ensure_token()

        # Fetch device info from device list
        payload = {
            "status": "",
            "alias": "",
            "pageSize": 10,
            "realName": "",
            "deviceType": "",
            "pageNum": 1,
            "deviceSn": self.device_sn,
            "plantName": "",
            "orgName": "",
            "deviceModel": "",
        }
        try:
            resp = await self._post(f"{API_BASE_URL}{ENDPOINT_DEVICE_LIST}", payload)
            data = await resp.json()
            if self._is_auth_error(resp.status, data):
                self.token = None
                await self._login()
                resp = await self._post(
                    f"{API_BASE_URL}{ENDPOINT_DEVICE_LIST}", payload
                )
                data = await resp.json()

            if data.get("code") == 200:
                for device in data.get("data", {}).get("dataList", []):
                    if device.get("deviceSn") == self.device_sn:
                        self.device_model = device.get("deviceModel")
                        self.device_alias = device.get("alias")
                        break
        except aiohttp.ClientError as err:
            # Surface connectivity problems so setup retries rather than
            # silently proceeding with missing device metadata.
            raise UpdateFailed(f"Failed to fetch device info: {err}") from err

        # Fetch timezone from plant list
        try:
            resp = await self._post(
                f"{API_BASE_URL}/app/plant/list_plant",
                {"status": "all", "pageSize": 10, "pageNum": 1},
            )
            data = await resp.json()
            if data.get("code") == 200:
                for plant in data.get("data", {}).get("dataList", []):
                    devices = plant.get("plantDeviceList", [])
                    for dev in devices:
                        if dev.get("deviceSn") == self.device_sn:
                            tz_str = plant.get("timeZone", "")
                            self.device_timezone = self._parse_utc_offset(tz_str)
                            _LOGGER.debug(
                                "Device timezone: %s -> %s",
                                tz_str,
                                self.device_timezone,
                            )
                            return
        except aiohttp.ClientError as err:
            _LOGGER.warning("Failed to fetch plant timezone: %s", err)

    async def _async_update_data(self) -> dict:
        """Fetch snapshot data from the API."""
        await self._ensure_token()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "collectorSn": "",
            "deviceSn": self.device_sn,
            "dateStr": now,
            "deviceType": "BP",
        }

        try:
            resp = await self._post(
                f"{API_BASE_URL}{ENDPOINT_DEVICE_SNAPSHOT}", payload
            )
            result = await resp.json()

            if self._is_auth_error(resp.status, result):
                self.token = None
                await self._login()
                retry_resp = await self._post(
                    f"{API_BASE_URL}{ENDPOINT_DEVICE_SNAPSHOT}", payload
                )
                if retry_resp.status != 200:
                    raise UpdateFailed(
                        f"API returned HTTP {retry_resp.status} after re-login"
                    )
                result = await retry_resp.json()
                if self._is_auth_error(retry_resp.status, result):
                    raise ConfigEntryAuthFailed(
                        "Login succeeded but API still rejected token"
                    )
            elif resp.status != 200:
                raise UpdateFailed(f"API returned HTTP {resp.status}")

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        code = result.get("code")
        if code == 401:
            raise ConfigEntryAuthFailed("API token expired or invalid")
        if code != 200:
            raise UpdateFailed(f"API returned code {code}: {result.get('msg', '')}")

        data = result.get("data", {})
        if not data:
            raise UpdateFailed("API returned empty data")

        return data
