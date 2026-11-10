# Voice Assistant

## Decoupling the Core from Local Devices

The `AssistantService` located in `core/main_engine/assistant_service.py` handles only text-based requests and selects the configured response engine. It does not access the microphone, trigger text-to-speech (TTS), or connect to a local database, making it suitable as a foundation for a backend process.

The existing `AssistantEngine` remains a local wrapper: it accepts text or records speech, invokes `AssistantService`, and—if necessary—provides an audible response. It supports `hybrid`, `llm`, and `actions` modes.

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
launching. The default `hybrid` mode runs recognized desktop commands through
the local allowlist and sends other questions to Ollama. Start Ollama with the
`llama3.2` model available before asking general questions. Use
`.\voice_venv\Scripts\python.exe -m core --mode llm` for LLM-only mode or
`.\voice_venv\Scripts\python.exe -m core --mode actions` for offline actions
only. Press Esc during spoken output to interrupt the answer; press Ctrl+C to
exit. Use `.\voice_venv\Scripts\python.exe -m core --help` for all options.

This repository currently provides a console runner, not a desktop GUI package
or a ready-to-use installer.

## ActionEngine Configuration

The ActionEngine configuration is split into focused YAML modules under
[core/cfgs/assistant](core/cfgs/assistant): `web.yaml` configures search and
site aliases, `shell.yaml` holds shell-command safety and behavior, and
`apps.yaml` / `processes.yaml` contain the application and process allowlists.
This keeps per-machine aliases separate from general behavior settings.

Users can add overrides without editing the built-in modules: create any
`.yaml` or `.yml` file in [core/cfgs/assistant.d](core/cfgs/assistant.d).
Overrides are loaded alphabetically by filename and recursively merged, so a
file can add or replace just a few entries. For example, an override may define
`shell.apps.my_editor: "app:My Editor"` or add a site alias under `web.sites`.
Only explicitly configured applications and exact safe commands are allowed;
arbitrary shell commands remain disabled.

The former `assistant.yaml` format is still supported as a compatibility
overlay between built-in modules and `assistant.d` overrides. Explicit
`ActionEngine(config_path=...)` continues to load the specified single file.
Closing an allowlisted process is immediate by default; set
`shell.confirm_process_close: true` to require one of `shell.confirm_words`.
To use actions via the main controller, create an `AssistentEngine` with
`assistant_mode="actions"`; a standalone `ActionEngine()` loads the modular
configuration automatically.

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

`main_cfg.json` stores startup preferences; the ActionEngine configuration is
composed by `AssistantConfigLoader` in [core/config_manager.py](core/config_manager.py).
Invalid or non-mapping config files raise a clear `ValueError` rather than
silently being ignored.
