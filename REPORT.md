## Phase 1: vLLM Configuration
* `--gpu-memory-utilization 0.95`: Maximizes VRAM usage to leave maximum space for KV Cache.
* `--max-model-len 8192`: Limits context length to save memory, as prompts are 1.5K-3K tokens and outputs are short.
* `--enable-chunked-prefill`: Prevents long prompts from blocking the queue, essential for the P95 latency SLO.
* `--max-num-seqs 128`: Caps concurrent sequences to protect the server under load and ensure sufficient KV Cache per request.