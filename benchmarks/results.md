# Local model smoke test

Run on 2026-10-09 through NEXUS's Ollama streaming client. Hardware reported:
Intel Core i5 13th generation, 16.8 GB system RAM, NVIDIA RTX 4050 Laptop GPU
with 6,141 MiB VRAM. Results are small smoke tests and vary with model loading,
system load, and prompt wording; they do not establish general model quality.

## Structured output

Prompt: return exactly a JSON object containing `product = 13 * 17` and
`reversed_list`, with the array `alpha, beta, gamma` reordered to `gamma, beta,
alpha` while keeping each string unchanged.

| Model | Result | Wall time | Model load | Generation speed |
| --- | --- | ---: | ---: | ---: |
| `qwen2.5:7b` | Exact bare JSON; expected values | 11.756 s | 10.359 s | 25.04 tokens/s |
| `llama3.1:8b` | Correct JSON data wrapped in a Markdown fence | 12.437 s | 10.675 s | 20.79 tokens/s |

The first Qwen load took 20.889 s; the first structured prompt took 32.223 s
overall. That initial prompt said "reverse the literal string items," which
Qwen interpreted as reversing each string's characters. The table uses a
clarified prompt that explicitly says to reverse array element order and keep
each string unchanged.

## Basic arithmetic reasoning

Prompt: three pens at INR 12 each, paid INR 50; show multiplication, subtraction,
and change due in one sentence.

| Model | Result | Wall time | Model load | Generation speed |
| --- | --- | ---: | ---: | ---: |
| `qwen2.5:7b` | Correct: INR 36 total, INR 14 change | 12.769 s | 10.828 s | 26.18 tokens/s |
| `llama3.1:8b` | Correct: INR 36 total, INR 14 change | 14.508 s | 11.760 s | 21.52 tokens/s |

Qwen is the default based on these limited results. This does not test tool
calling, long-context work, hard reasoning, or performance under sustained use.
