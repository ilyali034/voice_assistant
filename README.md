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
not currently supported. The GUI client is located in a separate package,
`desktop_client`, and can be launched using `python -m desktop_client`. In the
settings, you can switch the LLM between a local Ollama instance and a remote
backend; "Command" mode is always executed locally on the laptop. Preferences
are stored via `QSettings`, while the API key is kept in the system's
credential store rather than in a configuration file.

Voice input is triggered by the "Voice" button or the F9 key when the client
window is active. The recording is processed locally using the `base` Whisper
model and stops after 0.8 seconds of silence, upon a second press of the
trigger, or after 15 seconds; if speech does not begin within 3 seconds, the
recording is canceled. When the microphone is enabled for the first time, the
Whisper model may be downloaded from the network. Responses are voiced via a local TTS engine using `pyttsx3`; this feature can be disabled via a checkbox. The network backend receives only the transcribed text. A global hotkey, wake word, and a desktop application installer have not yet been implemented.

Standalone mode uses a local `OllamaResponseEngine` by default.
Ready-to-use installers for the desktop application and the server have not yet been built.

## ActionEngine Configuration

The ActionEngine loads its settings from [assistant.yaml](core/cfgs/assistant.yaml). The following are configured within the YAML file:

- `shell.apps` — specific voice-command names and their corresponding application launch commands. Entries formatted as `app:Name` will search for a shortcut with that name in the Windows Start menu.
- `shell.processes` — specific aliases for processes that are permitted to be closed. Closing a process requires a separate verbal confirmation and is subject to a 20-second timeout.
- `shell.safe_prefixes` — a comprehensive list of permitted diagnostic commands. To prevent the addition of potentially dangerous arguments, only exact command matches are allowed; additional parameters are prohibited.
- `shell.blocked_regex` — an additional list of patterns used for blocking.
- `web.search_engine` and `web.sites` — the search engine and user-defined website names.

Example commands include: "open VS Code," "launch Telegram," "open the site example.com," "search the internet for the weather," and "close Telegram." To confirm the termination of a process, say one of the phrases listed in `shell.confirm_words`; to cancel, say "cancel."

Commands defined in `shell.safe_prefixes` are executed without a shell (`shell=False`), with an enforced timeout, and are recorded in an audit log. Arbitrary shell commands cannot be executed. Applications will only launch if their corresponding command is defined in `shell.apps`. To use actions via the main controller, create an `AssistentEngine` with `assistant_mode="actions"`. A separate `ActionEngine()` will automatically load the YAML configuration.
