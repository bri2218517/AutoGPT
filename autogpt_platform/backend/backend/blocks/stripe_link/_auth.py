"""
Stripe Link CLI — Credential definitions for AutoGPT blocks.

This file defines the credential types and helpers that Stripe Link blocks use.
Link CLI uses OAuth 2.0 Device Code Grant (RFC 8628), which produces standard
access_token + refresh_token pairs — so we store them as OAuth2Credentials.

AUTH FLOW NOTES:
  Link's auth is a Device Code flow (not Authorization Code):
    1. POST https://login.link.com/device/code
       → { device_code, user_code, verification_uri }
    2. User visits verification_uri, logs in, enters code phrase
    3. Poll POST https://login.link.com/device/token
       → { access_token, refresh_token, expires_in }

  This doesn't fit the current BaseOAuthHandler interface (which assumes
  Authorization Code Grant with redirects). See EXPLORATION.md for options.
  The recommended path is adding a BaseDeviceAuthHandler abstraction.

  For now, this file defines the credential *shape* that blocks expect,
  independent of how the credentials are obtained.
"""

from typing import Literal

from pydantic import SecretStr

from backend.data.model import (
    CredentialsField,
    CredentialsMetaInput,
    OAuth2Credentials,
)
from backend.integrations.providers import ProviderName

# ---------------------------------------------------------------------------
# Provider name — would need to be added to the ProviderName enum, but the
# enum supports dynamic values via _missing_() so this works without changes.
# ---------------------------------------------------------------------------
STRIPE_LINK_PROVIDER = ProviderName("stripe_link")

# ---------------------------------------------------------------------------
# Link API constants
# ---------------------------------------------------------------------------
LINK_AUTH_BASE_URL = "https://login.link.com"
LINK_API_BASE_URL = "https://api.link.com"
LINK_CLIENT_ID = "lwlpk_U7Qy7ThG69STZk"
LINK_DEFAULT_SCOPES = ["userinfo:read", "payment_methods.agentic"]

# ---------------------------------------------------------------------------
# Credential type definitions
#
# Link CLI produces OAuth2 tokens (access_token + refresh_token), so we use
# OAuth2Credentials. The blocks don't care how the tokens were obtained —
# they just need a valid access_token for Bearer auth against api.link.com.
# ---------------------------------------------------------------------------
StripeLinkCredentials = OAuth2Credentials

StripeLinkCredentialsInput = CredentialsMetaInput[
    Literal[ProviderName.STRIPE_LINK],  # type: ignore[index]
    Literal["oauth2"],
]


def StripeLinkCredentialsField() -> StripeLinkCredentialsInput:
    """
    Creates a Stripe Link credentials input on a block.

    All Link blocks require the same `payment_methods.agentic` scope.
    """
    return CredentialsField(
        required_scopes=set(LINK_DEFAULT_SCOPES),
        description=(
            "Connect your Stripe Link account to enable the agent to request "
            "secure, one-time-use payment credentials from your Link wallet. "
            "You'll approve each spend request via the Link app."
        ),
    )


# ---------------------------------------------------------------------------
# Test credentials for block testing
# ---------------------------------------------------------------------------
TEST_CREDENTIALS = OAuth2Credentials(
    id="01234567-89ab-cdef-0123-456789abcdef",
    provider="stripe_link",
    access_token=SecretStr("mock-link-access-token"),
    refresh_token=SecretStr("mock-link-refresh-token"),
    access_token_expires_at=None,  # Won't expire in tests
    scopes=LINK_DEFAULT_SCOPES,
    title="Mock Stripe Link credentials",
    username="test@example.com",
)

TEST_CREDENTIALS_INPUT = {
    "provider": TEST_CREDENTIALS.provider,
    "id": TEST_CREDENTIALS.id,
    "type": TEST_CREDENTIALS.type,
    "title": TEST_CREDENTIALS.title,
}
