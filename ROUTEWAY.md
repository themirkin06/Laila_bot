# Text provider

Laila is configured to use AI Horde with the selected model:

`koboldcpp/G4-MeroMero-26B-A4B-it-uncensored-heretic`

The provider and model are pinned in `ai.py`. Provider environment variables do not switch the bot to another service. There is no automatic text-provider fallback; if AI Horde is unavailable, the message fails with an error.

Pollinations is disabled and is not used as a provider or fallback.

