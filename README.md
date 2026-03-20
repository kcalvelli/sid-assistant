# SID Assistant — Smart Intent Dispatcher

A Home Assistant custom integration that makes your voice assistant **fast for device control** and **smart for everything else**.

## The Problem

Every existing HA conversation agent integration (OpenAI, Anthropic, Ollama, etc.) sends **all** voice commands to the LLM — including simple device commands like "turn on the kitchen lights." That means every light switch command takes 10-30 seconds while the LLM processes the request, reasons about tool calls, executes them, and generates a response. Home Assistant can handle these commands locally in **milliseconds**.

## The Solution

SID tries Home Assistant's built-in intent system **first**. If it matches and executes a device command (lights, switches, covers, scenes, etc.), the action happens instantly. Then SID forwards the context to your LLM so it can acknowledge what happened in character — your pirate assistant says "Aye, lights are on!" without having been the one to turn them on.

If the local intent system doesn't match (questions, conversations, complex requests), SID falls through to your LLM with the full request for normal processing — along with your current entity states so the LLM knows what's available.

```
Voice Command
     │
     ▼
┌─────────────────────┐
│  HA Local Intents    │
│  (instant execution) │
└─────────┬───────────┘
          │
    ┌─────┴─────┐
    │           │
 Matched    No match
    │           │
    ▼           ▼
┌─────────┐ ┌─────────────┐
│ LLM:    │ │ LLM:        │
│ Ack     │ │ Full request│
│ only    │ │ + entities  │
└─────────┘ └─────────────┘
```

**Result:** "Turn on the lights" completes in ~1 second (local action + LLM acknowledgment) instead of 10-30 seconds.

## Compatibility

Works with any OpenAI-compatible `/v1/chat/completions` endpoint:

- **OpenAI** (GPT-4o, GPT-4o-mini, etc.)
- **Anthropic** (via OpenAI-compatible proxy)
- **Ollama**
- **LM Studio**
- **OpenRouter**
- **vLLM**
- **Any other OpenAI-compatible API**

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `kcalvelli/sid-assistant` with category **Integration**
4. Search for "SID Assistant" and install
5. Restart Home Assistant

### Manual

Copy the `custom_components/sid_assistant` directory into your Home Assistant `custom_components/` directory and restart.

## Configuration

1. Go to **Settings → Integrations → Add Integration**
2. Search for **SID Assistant**
3. Enter:
   - **Endpoint URL** — your chat completions URL (e.g., `http://localhost:11434/v1/chat/completions` for Ollama)
   - **Bearer Token** — API key or auth token for your endpoint
   - **Model** — model name to send in requests (e.g., `gpt-4o-mini`, `llama3`, etc.)
   - **Timeout** — request timeout in seconds (default: 60)
4. Go to **Settings → Voice Assistants** → select your assistant
5. Set **Conversation agent** to **SID**
6. **Disable** "Prefer handling commands locally" — SID handles the local-first logic itself

### Runtime Options

After setup, go to **Settings → Integrations → SID Assistant → Configure** to adjust:

- **Request Timeout** — override the timeout set during initial setup without removing the integration
- **System Prompt** — system message sent with full LLM requests (when local intents can't handle the command). Use this to tell your LLM what it can do, what entities are available, room aliases, and common patterns
- **Acknowledge Prompt** — system message sent when a local action was already completed. This is where you inject personality:

> *"You are a sarcastic British butler. When the user's smart home command has been completed, acknowledge it with dry wit."*

The default acknowledge prompt is neutral — it just tells the LLM an action was completed and to acknowledge briefly.

## Entity Context

When a command falls through to the LLM (full request path), SID automatically includes a snapshot of your current entity states. This gives the LLM awareness of your home without you needing to describe it in the system prompt.

**Included entities:**
- **Controllable** — lights, switches, climate, covers, fans, media players, locks
- **Sensors** — temperature and humidity sensors
- **Presence** — motion, occupancy, and presence binary sensors

**Filtered out** to keep the payload small:
- Noisy switch entities (auto-update, cloud connection, mute, do-not-disturb, loudness, crossfade, microphone)
- Sensor entities without useful device classes (power consumption, signal levels, battery, etc.)
- Entities in `unavailable` or `unknown` state

Climate entities include current and target temperature. Media players that are actively playing include track and artist info.

Entity states are fetched live on every request — new entities added to HA appear automatically.

## How It Works

1. **Voice command arrives** via your HA voice pipeline (Whisper, etc.)
2. SID calls `conversation.async_converse()` with the built-in `homeassistant` agent
3. If the local agent returns `ACTION_DONE` **with affected targets** (entities that were actually changed):
   - The action already happened — lights are on, door is locked, etc.
   - SID sends the context to your LLM: what the user said, what action completed, which entities were affected
   - Your LLM returns a personality-appropriate acknowledgment
   - That acknowledgment is spoken back via TTS
4. If the local agent returns anything else (no match, query, error):
   - SID forwards the original user text to your LLM with the system prompt and current entity states
   - Full LLM processing — the LLM can answer questions about device states, temperatures, occupancy, etc.
   - Response is spoken back via TTS

## License

MIT
