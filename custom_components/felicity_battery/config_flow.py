"""Config flow for Felicity Battery integration."""

from __future__ import annotations

import base64
import logging
import ssl
from typing import Any

import aiohttp
import voluptuous as vol
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_BASE_URL,
    API_HEADERS,
    CONF_DEVICE_SN,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ENDPOINT_DEVICE_LIST,
    LOGIN_URL,
    RSA_PUBLIC_KEY,
)
from .ssl_context import get_ssl_context

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=10)
        ),
    }
)


def encrypt_password(password: str, public_key_b64: str) -> str:
    """RSA-encrypt the password using the server's public key."""
    pem = f"-----BEGIN PUBLIC KEY-----\n{public_key_b64}\n-----END PUBLIC KEY-----"
    public_key = serialization.load_pem_public_key(pem.encode())
    encrypted = public_key.encrypt(password.encode(), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode()


async def async_login(
    session: aiohttp.ClientSession,
    username: str,
    password: str,
    ssl_ctx: ssl.SSLContext | None = None,
) -> str:
    """Login to the FSolar API and return the JWT token."""
    encrypted_pw = encrypt_password(password, RSA_PUBLIC_KEY)
    async with session.post(
        f"{API_BASE_URL}{LOGIN_URL}",
        json={
            "userName": username,
            "password": encrypted_pw,
            "registrationId": "",
            "version": "1.0",
        },
        headers=API_HEADERS,
        ssl=ssl_ctx,
    ) as resp:
        data = await resp.json()
        if data.get("code") == 200:
            return data["data"]["token"]
        raise ValueError(data.get("message", "Login failed"))


async def async_fetch_devices(
    session: aiohttp.ClientSession,
    token: str,
    ssl_ctx: ssl.SSLContext | None = None,
) -> list[dict]:
    """Fetch all devices from the FSolar API."""
    headers = dict(API_HEADERS)
    headers["Authorization"] = token
    async with session.post(
        f"{API_BASE_URL}{ENDPOINT_DEVICE_LIST}",
        ssl=ssl_ctx,
        json={
            "status": "",
            "alias": "",
            "pageSize": 50,
            "realName": "",
            "deviceType": "",
            "pageNum": 1,
            "deviceSn": "",
            "plantName": "",
            "orgName": "",
            "deviceModel": "",
        },
        headers=headers,
    ) as resp:
        data = await resp.json()
        if data.get("code") != 200:
            raise ValueError(data.get("message", "Failed to fetch devices"))
        return data.get("data", {}).get("dataList", [])


class FelicityBatteryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Felicity Battery."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._token: str | None = None
        self._devices: list[dict] = []
        self._user_input: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the credentials step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            try:
                session = async_get_clientsession(self.hass)
                ssl_ctx = await self.hass.async_add_executor_job(get_ssl_context)
                token = await async_login(session, username, password, ssl_ctx=ssl_ctx)
                devices = await async_fetch_devices(session, token, ssl_ctx=ssl_ctx)
            except ValueError:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"
            else:
                self._token = token
                self._devices = devices
                self._user_input = user_input

                if not devices:
                    errors["base"] = "no_devices"
                elif len(devices) == 1:
                    # Auto-select the only device
                    device = devices[0]
                    device_sn = device["deviceSn"]
                    await self.async_set_unique_id(device_sn)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"Felicity Battery {device.get('alias', device_sn)}",
                        data={**user_input, CONF_DEVICE_SN: device_sn},
                    )
                else:
                    return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the device selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_sn = user_input[CONF_DEVICE_SN]
            await self.async_set_unique_id(device_sn)
            self._abort_if_unique_id_configured()

            # Find alias for a nicer title
            alias = device_sn
            for device in self._devices:
                if device["deviceSn"] == device_sn:
                    alias = device.get("alias", device_sn)
                    break

            return self.async_create_entry(
                title=f"Felicity Battery {alias}",
                data={**self._user_input, CONF_DEVICE_SN: device_sn},
            )

        # Build device options: "alias (model) - SN"
        device_options = {}
        for device in self._devices:
            sn = device["deviceSn"]
            alias = device.get("alias", sn)
            model = device.get("deviceModel", "")
            label = f"{alias} ({model}) - {sn}" if model else f"{alias} - {sn}"
            device_options[sn] = label

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_SN): vol.In(device_options),
                }
            ),
            errors=errors,
        )
