# NEXUS: Local AI Brain

NEXUS is a local-first conversational assistant. It talks to Ollama on this
computer, streams responses, and keeps separate saved chat sessions in SQLite.
The default setup makes no cloud requests and does not write chat text to logs.

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

NEXUS runs in the terminal. Ask it to open File Explorer, Chrome, or YouTube
(for example, “open Chrome” or “open YouTube”). These are fixed local actions;
other requests continue to the local chat model.

### Speech

Running `python app.py` starts voice mode automatically. It listens for one
phrase at a time and speaks its replies. Say “Hey Nexus”
for an audible “I’m listening” cue, then say your request, or say the wake
phrase and request together (for example, “Hey Nexus, open Chrome”). A short
pause submits each phrase. NEXUS prints what it heard and speaks its response.
Use `python app.py --text` or say “text mode” to switch to typing. Use `/voice`
to switch back, or say “exit” to close NEXUS. Speech
recognition uses the installed Windows English recognizer. Replies use the
local Piper `en_US-lessac-medium` voice. On a fresh install, add Piper and
download the voice once:

```powershell
python -m pip install -e .
python -m piper.download_voices en_US-lessac-medium --data-dir data/voices
```

The voice model is about 63 MB and stays in the ignored local `data/voices`
folder. Make sure Windows has a default microphone and speaker selected.

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
smoke-test results, not a broad quality guarantee. Beyond local speech input
and output and the fixed Explorer, Chrome, and YouTube launch actions, screen
access and general PC control are not implemented.

## Architecture

- `nexus/config.py`: validated environment configuration
- `nexus/models/base.py`: provider-neutral chat interface
- `nexus/models/ollama_provider.py`: Ollama health check and NDJSON streaming
- `nexus/agent/conversation.py`: bounded, transactional conversation history
- `nexus/agent/memory.py`: separate chat sessions and transcript persistence in local SQLite
- `nexus/logging_config.py`: concise logs that omit prompts and replies
- `app.py`: diagnostics and interactive terminal loop
- `nexus/agent/desktop_actions.py`: allowlisted Explorer, Chrome, and YouTube launch actions
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
