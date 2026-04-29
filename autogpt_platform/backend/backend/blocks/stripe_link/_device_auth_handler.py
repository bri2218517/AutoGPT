"""
Skeleton for a Device Code OAuth handler for Stripe Link.

This would live in backend/integrations/oauth/ once the device-code flow
is officially supported. It shows what an implementation of Option C from
EXPLORATION.md would look like.

NOTE: This is exploration code — it won't work until:
  1. BaseDeviceAuthHandler (or equivalent) is added to the framework
  2. New API endpoints for device-auth initiation and polling are added
  3. Frontend UI for the device-code flow is implemented
"""

import logging
import time
from dataclasses import dataclass
from typing import ClassVar

import httpx
from pydantic import SecretStr

from backend.data.model import OAuth2Credentials
from backend.integrations.providers import ProviderName

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LINK_AUTH_BASE_URL = "https://login.link.com"
LINK_CLIENT_ID = "lwlpk_U7Qy7ThG69STZk"
DEFAULT_SCOPES = ["userinfo:read", "payment_methods.agentic"]


# ---------------------------------------------------------------------------
# Data classes for the device code flow
# ---------------------------------------------------------------------------
@dataclass
class DeviceAuthInitiation:
    """Returned when initiating the device code flow."""

    device_code: str
    user_code: str
    verification_url: str
    verification_url_complete: str
    expires_in: int
    interval: int  # seconds between polls


# ---------------------------------------------------------------------------
# Handler implementation
#
# This CANNOT extend BaseOAuthHandler because the interface doesn't match.
# Instead, this shows what a new BaseDeviceAuthHandler or a standalone
# handler class would look like.
# ---------------------------------------------------------------------------
class StripeLinkDeviceAuthHandler:
    """
    Handles the OAuth 2.0 Device Code Grant for Stripe Link.

    Flow:
      1. initiate_device_auth() → DeviceAuthInitiation
         - POST /device/code with client_id + scope
         - Returns verification URL for user + device_code for polling

      2. poll_for_tokens(device_code) → OAuth2Credentials | None
         - POST /device/token with grant_type=device_code
         - Returns None while pending, raises on denial/expiry
         - Returns OAuth2Credentials on approval

      3. refresh_tokens(credentials) → OAuth2Credentials
         - POST /device/token with grant_type=refresh_token
         - Standard refresh flow

      4. revoke_tokens(credentials) → bool
         - POST /device/revoke
    """

    PROVIDER_NAME: ClassVar[ProviderName] = ProviderName("stripe_link")

    async def initiate_device_auth(
        self,
        scopes: list[str] | None = None,
        client_name: str = "AutoGPT",
    ) -> DeviceAuthInitiation:
        """Start the device code flow. Returns URLs for the user to visit."""
        import socket

        effective_scopes = " ".join(scopes or DEFAULT_SCOPES)
        hostname = socket.gethostname()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{LINK_AUTH_BASE_URL}/device/code",
                data={
                    "client_id": LINK_CLIENT_ID,
                    "scope": effective_scopes,
                    "connection_label": f"{client_name} on {hostname}",
                    "client_hint": client_name,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        return DeviceAuthInitiation(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_url=data["verification_uri"],
            verification_url_complete=data["verification_uri_complete"],
            expires_in=data["expires_in"],
            interval=data["interval"],
        )

    async def poll_for_tokens(self, device_code: str) -> OAuth2Credentials | None:
        """
        Poll for token completion. Returns None if still pending.
        Raises on expiry or denial.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{LINK_AUTH_BASE_URL}/device/token",
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": LINK_CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code == 200:
            data = response.json()
            return OAuth2Credentials(
                provider=self.PROVIDER_NAME,
                access_token=SecretStr(data["access_token"]),
                refresh_token=SecretStr(data["refresh_token"]),
                access_token_expires_at=int(time.time()) + data["expires_in"],
                scopes=DEFAULT_SCOPES,
                title="Stripe Link",
            )

        if response.status_code == 400:
            error = response.json()
            error_code = error.get("error", "")

            if error_code in ("authorization_pending", "slow_down"):
                return None  # Still waiting for user

            if error_code == "expired_token":
                raise RuntimeError(
                    "Device code expired. Please restart the login flow."
                )

            if error_code == "access_denied":
                raise RuntimeError("Authorization denied by user.")

        raise RuntimeError(
            f"Unexpected response from Link auth: {response.status_code} "
            f"{response.text}"
        )

    async def refresh_tokens(self, credentials: OAuth2Credentials) -> OAuth2Credentials:
        """Refresh an expired access token using the refresh token."""
        if not credentials.refresh_token:
            raise RuntimeError("No refresh token available")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{LINK_AUTH_BASE_URL}/device/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": credentials.refresh_token.get_secret_value(),
                    "client_id": LINK_CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        credentials.access_token = SecretStr(data["access_token"])
        credentials.refresh_token = SecretStr(data["refresh_token"])
        credentials.access_token_expires_at = int(time.time()) + data["expires_in"]
        return credentials

    async def revoke_tokens(self, credentials: OAuth2Credentials) -> bool:
        """Revoke the refresh token at the Link auth server."""
        if not credentials.refresh_token:
            return False

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{LINK_AUTH_BASE_URL}/device/revoke",
                data={
                    "client_id": LINK_CLIENT_ID,
                    "token": credentials.refresh_token.get_secret_value(),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        return response.status_code == 200

    def needs_refresh(self, credentials: OAuth2Credentials) -> bool:
        """Check if the access token needs refreshing (5-minute window)."""
        if credentials.access_token_expires_at is None:
            return False
        return credentials.access_token_expires_at < int(time.time()) + 300
