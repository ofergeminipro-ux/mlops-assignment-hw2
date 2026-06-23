# Text-to-SQL Agent Project Report

## Phase 1: vLLM Configuration
* `--gpu-memory-utilization 0.95`: Maximizes VRAM usage to leave maximum space for KV Cache.
* `--max-model-len 8192`: Limits context length to save memory, as prompts are 1.5K-3K tokens and outputs are short.
* `--enable-chunked-prefill`: Prevents long prompts from blocking the queue, essential for the P95 latency SLO.
* `--max-num-seqs 128`: Caps concurrent sequences to protect the server under load and ensure sufficient KV Cache per request.

*(Note: Configuration was later adjusted in Phase 6 to meet SLO targets under load).*

![vLLM Manual Query Validation](screenshots/vllm_manual_query.png)

## Phase 2 & 4: Observability and Agentic Loop
The system utilizes a standard observability stack (Prometheus & Grafana) to monitor vLLM performance, alongside Langfuse to trace the LangGraph agent logic. The agent loop is designed to generate SQL, execute it, and revise it if the initial execution fails.

![Grafana Initial Serving State](screenshots/grafana_serving.png)

Metadata (tags) are successfully passed from the FastAPI request directly into the Langfuse trace using Langchain's configuration callbacks, enabling precise experiment tracking.

![Langfuse Metadata and Tags](screenshots/langfuse_tags.png)
![Langfuse Execution Trace](screenshots/langfuse_trace.png)

## Phase 5: Baseline Evaluation
A baseline evaluation was executed on 30 queries from the BIRD database. 

**Evaluation Results (`eval_baseline.json`):**
* Iteration 1 Pass Rate: 30.0%
* Iteration 2 Pass Rate: 33.3%
* Iteration 3 Pass Rate: 33.3%
* **Overall Accuracy:** 33.3%

**Analysis:** The agentic loop (specifically the `verify` -> `revise` flow) successfully identified and corrected erroneous queries, improving the baseline accuracy from 30% to 33.3% by the second iteration.

![Grafana During Evaluation Run](screenshots/grafana_eval_run.png)

## Phase 6: SLOs & Tuning

### The Bottleneck (Before Tuning)
Under a load test of 10 RPS (`duration: 300s`), the system failed to meet the E2E latency SLO of <5 seconds. P99 and P95 latencies spiked to nearly 2 minutes. 
**Diagnosis:** The agent repeatedly sends massive database schemas to the model during the `generate`, `verify`, and `revise` steps. Without caching, vLLM was forced to recompute the prefill phase for the same text on every request, causing the Time-To-First-Token (TTFT) to skyrocket and heavily bottlenecking the GPU, while the KV Cache remained underutilized (below 20%).

![Grafana Before Tuning - High Latency](screenshots/grafana_before.png)

### The Solution (Tuning Applied)
To resolve this, the vLLM startup script was modified. We added `--enable-prefix-caching` (and removed `--enable-chunked-prefill` to avoid feature collisions and prioritize system prompt caching). This allows the engine to store the massive schema context in the KV Cache and reuse it across iterations.

### The Results (After Tuning)
Following the optimization, a second load test demonstrated complete stability:
* **TTFT** dropped to near-zero after the initial schema load.
* **KV Cache Usage** increased as the server efficiently managed context.
* **E2E Latency (P95)** stabilized at **~1.4 seconds**, easily passing the <5s SLO requirement.

![Grafana After Tuning - Stable Latency](screenshots/grafana_after.png)

### Final Quality Sanity Check
A final evaluation run (`eval_after_tuning.json`) confirmed that the optimizations did not degrade the agent's reasoning capabilities. The overall accuracy remained exactly at **33.3%**.

## What I'd Do With More Time
If I had more time, I would focus on two main improvements:
1. **Dynamic Schema Retrieval:** Instead of injecting the entire database schema into the prompt, I would implement a lightweight retriever to fetch only the relevant tables. This would drastically reduce prompt length, further decreasing prefill times and saving KV cache space.
2. **Few-Shot Prompting:** To boost the 33.3% accuracy rate, I would dynamically retrieve and inject relevant successful SQL examples (few-shot) into the `generate` node prompt based on semantic similarity to the user's question.