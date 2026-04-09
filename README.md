# AIPS Traffic Counter

An algorithmic event-stream processor designed to parse, aggregate, and evaluate multi-day vehicle traffic logs without bounding data structures to memory.

## 🎯 The Objective

The system consumes machine-generated traffic counter logs (recording the number of vehicles passing a sensor per half-hour) and calculates four core analytical metrics:
1. **Total cars** observed over the entire recorded lifespan.
2. **Daily aggregated totals** for each day in the sequence.
3. The **Top 3 highest traffic half-hours** globally.
4. The **1.5-hour contiguous period** (3 consecutive 30m blocks) exhibiting the lowest traffic.

---

## 🏗️ Architecture & Algorithmic Complexity

This solution abandons naive array-buffering (`O(N)` memory) in favor of a strictly generic **Object-Oriented Event Stream** relying purely on the Python standard library, achieving absolute scalability.

### 1. Streaming Ingestion
* **Implementation:** `Iterator[tuple[datetime, int]]` via `read_file_data`.
* **Complexity:** Space complexity is strictly **$O(1)$** during read times (excluding the tiny day-count dictionary map footprint). You can feed a 50GB file into this system without Out-Of-Memory (OOM) crashes.

### 2. The "Top 3" Strategy (Min-Heap)
* **Implementation:** A strictly bounded `heapq` (Min-Heap of size `K=3`).
* **Complexity:** Time complexity shifts from a full sort **$O(N \log N)$** down to **$O(N \log 3)$**. 
* **Tie-Breaking Engine:** Custom Dunder methods (`__lt__`) force the Heap to retain chronologically older elements during capacity ejections on identical counts.

### 3. sliding Window 
* **Implementation:** A sliding array constraint resetting upon `timedelta != 30`.
* **Complexity:** Operates inline at **$O(1)$** spatial and **$O(N)$** temporal complexity perfectly tracking the 3-block contiguity rules.

---

## 📜 Assumptions & Data Contracts

1. **Input Format:** 
   - `datetime` (as ISO 8601 formatted timestamp) 
   - `count` (as an integer)
2. **Input Delimiters:** It is assumed that the data is provided in a `csv` file, with `datetime` and `count` as unnamed columns, separated by whitespace (e.g. `2021-12-01T05:00:00 5`, strict CSV commas will trigger ingestion validation failures)
3. **Missing Observations:** Missing hourly bounds (e.g., jumping from `18:00:00` straight to `19:00:00`) explicitly resets the Sliding Window search. Missing data is interpreted dynamically as corrupted bounds, not implicit `0` totals.
4. **Implicit Sorting:** The logs are treated as **chronologically-sorted** standard machine logs matching real-world stream configurations, given the spec has asked us to "assume clean input".
   - **NOTE**: Otherwise, we'd have to either microbatch sort the input data or use a more complex data structure to maintain the sliding window.
---

## 💻 Development & Setup

This project uses `uv` and `make` for packaging and automation. 

### Prerequisites
* 🦀 **`uv`**: Rust-backed Python package orchestrator (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
* 🐍 **Python 3.14+**

### Active Operations
Invoke the universal `Makefile` entrypoints to trigger local pipelines:

```bash
# Setup Environment & Sync Locks
make setup

# Apply Strict `ruff` Formatting and Fixes
make format

# Analyze Lints
make lint

# Static Type Enforcement via `mypy --strict`
make typecheck

# 100% Coverage Happy-Path Testing
make test
```

---

## 🤖 Meta Log (Methodology)

To maintain radical transparency, the engineering of this challenge was split as follows:
* **Hand-crafted:** The core Python logic processing, data class foundations, and the primary algorithm logic implementation was hand-crafted manually (with linewise auto-completion)
* **AI Orchestration (Gemini):** AI assistence was taken for the following tasks:
  * Algorithmic architectural review.
  * Docstring enforcement standardising Google-style conventions.
  * Initial scaffolding mapping `uv`, CI/CD yaml configuration, and Pytest coverage topologies.
