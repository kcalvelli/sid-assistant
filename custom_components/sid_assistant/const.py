"""Constants for the Smart Intent Dispatcher (SID) integration."""

DOMAIN = "sid_assistant"

CONF_ENDPOINT_URL = "endpoint_url"
CONF_BEARER_TOKEN = "bearer_token"
CONF_TIMEOUT = "timeout"
CONF_MODEL = "model"
CONF_ACKNOWLEDGE_PROMPT = "acknowledge_prompt"

DEFAULT_ENDPOINT_URL = ""
DEFAULT_TIMEOUT = 60
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_ACKNOWLEDGE_PROMPT = (
    "The user gave a voice command and the smart home action has ALREADY "
    "been completed by the local system. Do NOT attempt to perform the "
    "action again or call any tools. Just acknowledge what happened with "
    "a brief, natural response."
)
