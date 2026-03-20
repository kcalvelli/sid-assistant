"""Config flow for SID Assistant."""

from __future__ import annotations

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACKNOWLEDGE_PROMPT,
    CONF_BEARER_TOKEN,
    CONF_ENDPOINT_URL,
    CONF_FULL_REQUEST_PROMPT,
    CONF_MODEL,
    CONF_TIMEOUT,
    DEFAULT_ACKNOWLEDGE_PROMPT,
    DEFAULT_FULL_REQUEST_PROMPT,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENDPOINT_URL): str,
        vol.Required(CONF_BEARER_TOKEN): str,
        vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): str,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
    }
)


class SidAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SID Assistant."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow handler."""
        return SidAssistantOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _test_connection(
                    self.hass,
                    user_input[CONF_ENDPOINT_URL],
                    user_input[CONF_BEARER_TOKEN],
                    user_input.get(CONF_MODEL, DEFAULT_MODEL),
                    user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                )
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="SID Assistant", data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class SidAssistantOptionsFlow(OptionsFlow):
    """Handle options for SID Assistant."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options
        current_timeout = current.get(
            CONF_TIMEOUT,
            self._config_entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=current_timeout,
                    ): int,
                    vol.Optional(
                        CONF_ACKNOWLEDGE_PROMPT,
                        default=current.get(
                            CONF_ACKNOWLEDGE_PROMPT, DEFAULT_ACKNOWLEDGE_PROMPT
                        ),
                    ): str,
                    vol.Optional(
                        CONF_FULL_REQUEST_PROMPT,
                        default=current.get(
                            CONF_FULL_REQUEST_PROMPT, DEFAULT_FULL_REQUEST_PROMPT
                        ),
                    ): str,
                }
            ),
        )


async def _test_connection(
    hass, url: str, token: str, model: str, timeout: int
) -> None:
    """Test that we can reach the chat completions endpoint."""
    session = async_get_clientsession(hass)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    async with session.post(
        url,
        json=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as resp:
        resp.raise_for_status()
