# Voice Assistant

## Decoupling the Core from Local Devices

The `AssistantService` located in `core/main_engine/assistant_service.py` handles only text-based requests and selects the configured response engine. It does not access the microphone, trigger text-to-speech (TTS), or connect to a local database, making it suitable as a foundation for a backend process.

The existing `AssistantEngine` remains a local wrapper: it accepts text or records speech, invokes `AssistantService`, and—if necessary—provides an audible response. Its current constructor and `llm`/`actions` modes have been preserved.

This represents the first phase of an architectural separation. The HTTP API, remote client, and standalone/server builds will continue to evolve independently; the HTTP API and a remote response client are already available as Python components.

## Backend and Remote Client

The backend is instantiated via `create_app(service, api_key)` in `core/api/app.py`. It accepts only text-based requests, with a limit of 1,800 characters. The `GET /health` endpoint checks for availability, while `POST /v1/requests` requires an `Authorization: Bearer <key>` header. An API key is mandatory. To process requests, the backend utilizes only the LLM engine; it does not initialize the microphone, TTS, Qdrant, or the local `ActionEngine`.

To install only the server-side dependencies, use `requirements-server.txt`; this file excludes local STT/TTS and Qdrant packages. A configured backend can be launched by running `python -m core.api.server`. Before
launch, you must set `ASSISTANT_API_KEY` and, if necessary, `ASSISTANT_HOST`,
`ASSISTANT_PORT`, `ASSISTANT_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_TIMEOUT_S`, and
`ASSISTANT_LANGUAGE`. By default, the server listens only on `127.0.0.1`. For
remote access, set `ASSISTANT_HOST=0.0.0.0` and place the API behind an
HTTPS reverse proxy; do not expose an unencrypted HTTP backend directly to the
internet. The client allows plain HTTP only for localhost.

On the laptop, `RemoteResponseEngine` from
`core/main_engine/remote_client.py` implements the same interface as the local
LLM. It can be passed to `AssistentEngine` via the `llm_engine` parameter; the
microphone, TTS, and `ActionEngine` remain local. Audio backend streaming is
not currently supported.

## Run the local voice assistant on Windows

From the project root, install the dependencies and start the assistant:

```powershell
.\voice_venv\Scripts\python.exe -m pip install -r requirements.txt
.\voice_venv\Scripts\python.exe -m core
```

The bundled Vosk Russian model is used for microphone input. Speech output uses
an installed Windows voice matching `--lang` (for Russian, Microsoft Irina is
used when available). Connect a microphone and speakers/headphones before
launching. The default `actions` mode runs local allowlisted desktop actions
without Ollama. For generated answers, start Ollama with the `llama3.2` model
available and run `.\voice_venv\Scripts\python.exe -m core --mode llm`.
Use `.\voice_venv\Scripts\python.exe -m core --help` to see options such as
language, model, and wake word. Press Ctrl+C to stop the assistant.

This repository currently provides a console runner, not a desktop GUI package
or a ready-to-use installer.

## ActionEngine Configuration

The ActionEngine loads its settings from [assistant.yaml](core/cfgs/assistant.yaml). The following are configured within the YAML file:


Example commands include: "open VS Code," "launch Telegram," "open the site example.com," "search the internet for the weather," and "close Telegram." To confirm the termination of a process, say one of the phrases listed in `shell.confirm_words`; to cancel, say "cancel."

Commands defined in `shell.safe_prefixes` are executed without a shell (`shell=False`), with an enforced timeout, and are recorded in an audit log. Arbitrary shell commands cannot be executed. Applications will only launch if their corresponding command is defined in `shell.apps`. To use actions via the main controller, create an `AssistentEngine` with `assistant_mode="actions"`. A separate `ActionEngine()` will automatically load the YAML configuration.

## Configuration files

Project configuration files live under `core/cfgs`. `ConfigStore` in
`core/cfg.py` resolves paths relative to the project rather than the current
working directory, supports JSON and YAML, and writes changes atomically. A
missing file can be initialized with defaults:

```python
from core.cfg import ConfigStore

store = ConfigStore()
settings = store.load("my_settings.json", {"language": "ru"})
settings["language"] = "en"
store.save("my_settings.json", settings)
```

`main_cfg.json` stores startup preferences; `assistant.yaml` stores the
ActionEngine allowlists and behavior settings. Invalid or non-mapping config
files raise a clear `ValueError` rather than silently being ignored.
