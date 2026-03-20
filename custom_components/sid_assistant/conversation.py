"""Conversation agent for SID Assistant (Smart Intent Dispatcher)."""

from __future__ import annotations

import logging
from typing import Literal

import aiohttp

from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationEntity, ConversationResult
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
)

_LOGGER = logging.getLogger(__name__)

HOME_ASSISTANT_AGENT = "conversation.home_assistant"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SID conversation entity."""
    async_add_entities([SidConversationEntity(entry)])


class SidConversationEntity(
    ConversationEntity, conversation.AbstractConversationAgent
):
    """Smart Intent Dispatcher conversation agent entity."""

    _attr_has_entity_name = True
    _attr_name = "SID"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the entity."""
        self._entry = entry
        self._attr_unique_id = entry.entry_id

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return "*"

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> ConversationResult:
        """Process a conversation turn.

        Phase 1: Try HA's local intent system for instant device control.
        Phase 2: If local didn't handle it, forward to the LLM endpoint.
        """
        local_result = await conversation.async_converse(
            hass=self.hass,
            text=user_input.text,
            conversation_id=None,
            context=user_input.context,
            language=user_input.language,
            agent_id=HOME_ASSISTANT_AGENT,
        )

        response_data = local_result.response.as_dict()
        has_targets = bool(response_data.get("data", {}).get("success"))

        _LOGGER.debug(
            "Local agent result: response_type=%s, has_targets=%s, speech=%s, data=%s",
            local_result.response.response_type,
            has_targets,
            response_data.get("speech"),
            response_data.get("data"),
        )

        if (
            local_result.response.response_type
            == intent.IntentResponseType.ACTION_DONE
            and has_targets
        ):
            return await self._llm_acknowledge(user_input, local_result)

        return await self._llm_full_request(user_input)

    async def _llm_acknowledge(
        self,
        user_input: conversation.ConversationInput,
        local_result: ConversationResult,
    ) -> ConversationResult:
        """Ask the LLM to acknowledge a completed local action."""
        response_data = local_result.response.as_dict()

        speech = response_data.get("speech", {}).get("plain", {}).get("speech", "")
        targets = _summarize_targets(response_data)

        system_msg = self._entry.options.get(
            CONF_ACKNOWLEDGE_PROMPT, DEFAULT_ACKNOWLEDGE_PROMPT
        )

        user_msg = (
            f"User said: \"{user_input.text}\"\n"
            f"Action completed: {speech}"
        )
        if targets:
            user_msg += f"\nAffected: {targets}"

        return await self._call_llm(user_input, system_msg, user_msg)

    async def _llm_full_request(
        self, user_input: conversation.ConversationInput
    ) -> ConversationResult:
        """Forward the raw user text to the LLM for full processing."""
        system_msg = self._entry.options.get(
            CONF_FULL_REQUEST_PROMPT, DEFAULT_FULL_REQUEST_PROMPT
        )
        entity_context = self._build_entity_context()
        user_msg = user_input.text
        if entity_context:
            user_msg = f"{user_msg}\n\n{entity_context}"
        return await self._call_llm(user_input, system_msg=system_msg, user_msg=user_msg)

    def _build_entity_context(self) -> str:
        """Build a compact summary of current entity states."""
        relevant_domains = {
            "light", "switch", "climate", "cover", "fan",
            "media_player", "lock",
        }
        lines: list[str] = []
        for state in self.hass.states.async_all():
            domain = state.domain
            if domain not in relevant_domains:
                continue
            if state.state in ("unavailable", "unknown"):
                continue
            name = state.attributes.get("friendly_name", state.entity_id)
            entry = f"- {name} ({state.entity_id}): {state.state}"
            # Include useful attributes for specific domains
            attrs = state.attributes
            if domain == "climate":
                if temp := attrs.get("current_temperature"):
                    entry += f", current={temp}"
                if target := attrs.get("temperature"):
                    entry += f", target={target}"
            elif domain == "media_player" and state.state == "playing":
                if title := attrs.get("media_title"):
                    entry += f", playing=\"{title}\""
                if artist := attrs.get("media_artist"):
                    entry += f" by {artist}"
            lines.append(entry)
        if not lines:
            return ""
        return "Available entities:\n" + "\n".join(sorted(lines))

    async def _call_llm(
        self,
        user_input: conversation.ConversationInput,
        system_msg: str | None,
        user_msg: str,
    ) -> ConversationResult:
        """Make an HTTP request to the chat completions endpoint."""
        url = self._entry.data[CONF_ENDPOINT_URL]
        token = self._entry.data[CONF_BEARER_TOKEN]
        model = self._entry.data.get(CONF_MODEL, DEFAULT_MODEL)
        timeout = self._entry.options.get(
            CONF_TIMEOUT,
            self._entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
        )

        messages: list[dict] = []
        if system_msg:
            messages.append({"role": "system", "content": system_msg})
        messages.append({"role": "user", "content": user_msg})

        payload = {
            "model": model,
            "messages": messages,
        }

        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        _LOGGER.debug("Calling LLM: url=%s, model=%s, messages=%s", url, model, messages)

        try:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

            _LOGGER.debug("LLM response: %s", data)
            reply = data["choices"][0]["message"]["content"]
        except (aiohttp.ClientError, TimeoutError, KeyError, IndexError) as err:
            _LOGGER.error("LLM request failed: %s", err)
            return _error_result(user_input, f"LLM is unavailable: {err}")
        except Exception:
            _LOGGER.exception("Unexpected error calling LLM")
            return _error_result(user_input, "LLM encountered an unexpected error.")

        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(reply)
        return ConversationResult(
            response=intent_response,
            conversation_id=user_input.conversation_id,
        )


def _error_result(
    user_input: conversation.ConversationInput, message: str
) -> ConversationResult:
    """Build an error ConversationResult."""
    intent_response = intent.IntentResponse(language=user_input.language)
    intent_response.async_set_error(
        intent.IntentResponseErrorCode.UNKNOWN, message
    )
    return ConversationResult(
        response=intent_response,
        conversation_id=user_input.conversation_id,
    )


def _summarize_targets(response_data: dict) -> str:
    """Extract a human-readable summary of affected targets."""
    data = response_data.get("data", {})
    targets = data.get("success", [])
    if not targets:
        return ""
    names = []
    for t in targets:
        name = t.get("name") or t.get("id", "unknown")
        names.append(name)
    return ", ".join(names)
