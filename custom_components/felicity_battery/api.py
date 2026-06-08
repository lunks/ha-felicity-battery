"""HTTP client helpers for the FSolar cloud API.

This module owns the login/RSA-encryption and device-listing logic so that
both the config flow and the coordinator can depend on it without creating a
layering inversion between them.
"""

from __future__ import annotations

import base64
import ssl

import aiohttp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .const import (
    API_BASE_URL,
    API_HEADERS,
    ENDPOINT_DEVICE_LIST,
    LOGIN_URL,
    RSA_PUBLIC_KEY,
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
