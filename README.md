# NEXUS: Local AI Brain

NEXUS Day 1 is a small, local-first conversational CLI. It talks to Ollama on
your own machine, streams responses, keeps a bounded in-memory transcript, and
uses only Python's standard library at runtime. The default setup makes no
cloud requests and does not write conversation text to logs or disk.

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

To measure a short response on the current local model:

```powershell
python benchmarks/benchmark_model.py
```

Chat commands: `/help`, `/clear`, `/exit`.

No Python packages need to be installed. The test suite uses only `unittest`:

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
smoke-test results, not a broad quality guarantee. No structured tool calling,
screen access, voice, persistent memory, or PC control is implemented in Day 1.

## Architecture

- `nexus/config.py`: validated environment configuration
- `nexus/models/base.py`: provider-neutral chat interface
- `nexus/models/ollama_provider.py`: Ollama health check and NDJSON streaming
- `nexus/agent/conversation.py`: bounded, transactional conversation history
- `nexus/logging_config.py`: concise logs that omit prompts and replies
- `app.py`: diagnostics and interactive terminal loop
- `tests/`: offline tests with a mocked Ollama HTTP API
- `benchmarks/benchmark_model.py`: one-prompt latency and Ollama generation metrics
- `benchmarks/results.md`: measured model comparison on this machine

Conversation history currently lives only in memory and is discarded at exit.
SQLite persistence can be added in a later milestone.
