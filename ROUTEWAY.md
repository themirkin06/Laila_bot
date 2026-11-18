# Routeway test provider

AI Horde remains the active provider until Routeway is explicitly selected and its key is present. Routeway errors never trigger an automatic provider fallback. Pollinations is not used for chat.

## Render environment variables

To test Routeway, set these variables on the Laila service in Render:

| Variable | Value |
| --- | --- |
| `LLM_PROVIDER` | `routeway` |
| `ROUTEWAY_API_KEY` | Enter your Routeway key in Render. It is intentionally not included in this repository. |
| `ROUTEWAY_MODEL` | `gemma-4-26b-a4b-it-meromero:free` (optional; this is the default) |

With `LLM_PROVIDER=routeway` but no `ROUTEWAY_API_KEY`, the bot keeps using AI Horde. Once you add the key, Routeway handles new messages. Routeway uses `https://api.routeway.ai/v1` and its OpenAI-compatible chat completions endpoint.

To return to AI Horde, set `LLM_PROVIDER=aihorde` or remove `LLM_PROVIDER`. Do not change `AI_HORDE_MODELS` or other AI Horde settings for this test. If Routeway returns an error after the key is added, that response fails rather than switching providers. The configured default model is Routeway's free MeroMero model.

Source: [Routeway OpenAI-compatible API documentation](https://docs.routeway.ai/getting-started/chat-uis) and [Gemma 4 26B MeroMero (Free) model page](https://routeway.ai/models/gemma-4-26b-a4b-it-meromero%3Afree).
