# NEXUS: Local AI Brain

NEXUS is a local-first conversational assistant. It talks to Ollama on this
computer, streams responses, and keeps separate saved chat sessions in SQLite.
Microphone audio is transcribed locally; the Whisper model downloads once on
first voice use. Chat requests go to the configured Ollama server. Chat text is
not written to logs.

## Requirements

- Windows, Python 3.11 or newer
- Ollama for Windows, running locally
- A model already installed in Ollama (this machine currently has
  `qwen2.5:7b`, `llama3.1:8b`, and `llava:7b`)

## Run

From this folder:

```powershell
python app.py --check
python app.py
```

NEXUS runs in the terminal. Ask it to open File Explorer, Chrome, YouTube,
Notepad, Calculator, Paint, Task Manager, or Windows Settings. Ask it to take a
screenshot to save a PNG in your Pictures folder. Basic arithmetic requests such
as `calculate (12 + 8) / 4` are evaluated locally. Other questions go to the
configured Ollama model.

### Speech

Running `python app.py` starts voice mode automatically. It listens for one
phrase at a time and speaks its replies. Say “Hey Nexus”
for an audible “I’m listening” cue, then say your request, or say the wake
phrase and request together (for example, “Hey Nexus, open Chrome”). A short
pause submits each phrase. NEXUS prints what it heard and speaks its response.
Use `python app.py --text` or say “text mode” to switch to typing. Use `/voice`
to switch back, or say “exit” to close NEXUS. Speech
recognition uses the local multilingual Whisper `small` model, which is more
robust to accents than the built-in Windows English recognizer. It defaults to
English for short spoken commands, records with a little audio before speech
starts, and sends the phrase after a pause. The first voice request downloads
the model (about 500 MB); later transcription runs locally. Replies use the
local Piper `en_US-lessac-medium` voice. On a fresh install, install the speech
and voice dependencies, then download the voice once:

```powershell
python -m pip install -e .
python -m piper.download_voices en_US-lessac-medium --data-dir data/voices
```

The Piper voice model is about 63 MB and stays in the ignored local
`data/voices` folder. Whisper's model is stored in the Hugging Face cache.
Make sure the default microphone and speaker are selected. Use
`NEXUS_WHISPER_MODEL=base` for a smaller/faster Whisper model, or
`NEXUS_WHISPER_DEVICE=cuda` when the CTranslate2 CUDA runtime is installed.

To measure a short response on the current local model:

```powershell
python benchmarks/benchmark_model.py
```

Chat commands: `/help`, `/clear`, `/exit`.

The test suite uses only `unittest`:

```powershell
python -m unittest discover -s tests -v
```

## Configuration

Settings are read from environment variables. Copy `.env.example` as a
reference; the application does not load `.env` automatically.

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXUS_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama API URL |
| `NEXUS_MODEL` | `qwen2.5:7b` | Installed Ollama model name |
| `NEXUS_TIMEOUT_SECONDS` | `120` | Request timeout |
| `NEXUS_NUM_CTX` | `4096` | Model context window requested from Ollama |
| `NEXUS_NUM_PREDICT` | `512` | Maximum generated tokens per reply |
| `NEXUS_TEMPERATURE` | `0.2` | Sampling variation; lower values make replies more consistent |
| `NEXUS_MAX_HISTORY_MESSAGES` | `12` | Maximum recent chat messages sent to the model |
| `NEXUS_MAX_MESSAGE_CHARS` | `12000` | Input and response safety limit |
| `NEXUS_MEMORY_DB` | `data/nexus.sqlite3` | Local SQLite file for recent chat history |
| `NEXUS_WHISPER_MODEL` | `small` | Local speech model; `base` uses less memory and runs faster |
| `NEXUS_WHISPER_LANGUAGE` | `en` | Spoken language; use `hi` for Hindi or `auto` for automatic detection |
| `NEXUS_WHISPER_DEVICE` | `cpu` | Transcription device; use `cuda` with CTranslate2 CUDA support installed |
| `NEXUS_WHISPER_COMPUTE_TYPE` | `int8` on CPU, `float16` on CUDA | Whisper inference precision |

The default URL is local-only. If you deliberately point it at another host,
chat contents will be sent to that host. Keep the URL free of credentials.

## Model choice and limitations

NEXUS uses `qwen2.5:7b` by default. It was selected from the models tested
because it returned the tested structured task as exact bare JSON and handled
the sample arithmetic task, with about 25 generated tokens/second in these
runs. Ollama reports 82% GPU / 18% CPU placement at a 4096-token context on
this machine's RTX 4050 with 6 GB VRAM, so it runs across GPU and system RAM.
`llama3.1:8b` and
`llava:7b` were already installed; Llama produced the correct tested JSON data
inside a Markdown fence and answered the arithmetic task. `llava:7b` is
vision-oriented and is not the selected text assistant. These are small
smoke-test results, not a broad quality guarantee. NEXUS can capture a
screenshot when asked, but it does not interpret the image or see the screen
during ordinary chat. Desktop access is limited to the listed launch actions
and screenshot capture; arbitrary application control is not implemented.
General answers come from the configured local model, so answer quality depends
on that model and its training data. The default setup does not search the web
for current facts.

## Architecture

- `nexus/config.py`: validated environment configuration
- `nexus/models/base.py`: provider-neutral chat interface
- `nexus/models/ollama_provider.py`: Ollama health check and NDJSON streaming
- `nexus/agent/conversation.py`: bounded, transactional conversation history
- `nexus/agent/memory.py`: separate chat sessions and transcript persistence in local SQLite
- `nexus/logging_config.py`: concise logs that omit prompts and replies
- `app.py`: diagnostics and interactive terminal loop
- `nexus/agent/desktop_actions.py`: allowlisted Windows app launch, screenshot capture, and arithmetic
- `nexus/agent/speech.py`: microphone transcription and local Piper speech output
- `tests/`: offline tests with a mocked Ollama HTTP API
- `benchmarks/benchmark_model.py`: one-prompt latency and Ollama generation metrics
- `benchmarks/results.md`: measured model comparison on this machine

Conversations are stored in `data/nexus.sqlite3`. NEXUS opens the most recent
chat at startup and keeps earlier sessions available. Only complete
user/assistant turns are saved. **Clear Chat** empties the selected session;
**Delete** removes that session. Existing single-chat databases are migrated
into a “Previous conversation” entry. The database is ignored by Git and is
local plaintext; anyone with access to this Windows account and file can read it.
