# Architecture & Performance Profiling Report

**Target Asset**: `main.py`
**Evaluator**: L7 AI Systems Architect (High Compute Tier)

## 1. System-2 Pre-Computation & Algorithmic Complexity

The existing pipeline correctly implements an `Iterator`-based generator to enforce lazily-evaluated data streaming, preventing the entire input corpus from saturating RAM. However, several underlying data structures introduce hidden, cumulative overhead.

### 1.1 Time Complexity (Big O) per Row
- **I/O & Parsing (`read_file_data`)**: $\mathcal{O}(1)$ per tick. The operations `line.split()` and `datetime.fromisoformat()` are string manipulations that incur high relative CPU overhead in the Python interpreter compared to vectorized ingestion.
- **Daily Window (`_update_daily`)**: $\mathcal{O}(1)$ average. Standard hash-map allocation.
- **Top 3 Filtering (`_update_top_3_half_hours`)**: $\mathcal{O}(\log(k))$ where $k \le 3$. Since $k$ is effectively constant, the bounded Min-Heap achieves optimal $\mathcal{O}(1)$ bounds. However, relying on a custom `__lt__` dunder method drops execution out of C-compiled `heapq` space back into the slower Python execution frame.
- **Sliding Contiguous Window (`_update_last_hour_and_half`)**: Evaluates as pseudo-$\mathcal{O}(1)$ but is structurally hindered by `self._last_hour_and_half.pop(0)`. Native Python lists are dynamic arrays; a `pop(0)` action incurs an $\mathcal{O}(M)$ penalty (where $M \le 3$) because all trailing pointers must be shifted left in memory. 
- **Minimum Threshold Validation (`_update_least_hour_and_half`)**: $\mathcal{O}(1)$. Requires iterating over $\le 3$ elements.

### 1.2 Space Complexity (Memory / VRAM bounds)
- **Peak RAM Payload**: Constant $\mathcal{O}(D_{\text{unique\_days}} + K_{\text{constant\_windows}})$. The `_daily` dict grows linearly alongside unique dates. All other data structures are rigorously capped at $\le 3$ active length bounds.
- **Object Fragmentation**: **Compute Bound Risk**. Every single row triggers `HalfHour(count, timestamp)`. If scaling to $10^8$ rows, Python must initialize, track, and Garbage Collect (GC) $10^8$ micro-objects in memory. This continuous thrashing of the allocator produces severe L1/L2 cache misses.

---

## 2. Bottleneck Analysis

When evaluating strict FTI (Feature, Training, Inference) pipelines, `main.py` encounters bottlenecks that would violate L7 scaling mandates if exposed to >1GB payloads:

### 2.1 The Compute/Interpreter Bound
Because raw iteration, string splitting, and loop control happens native to native Python instructions as opposed to releasing the GIL (Global Interpreter Lock) internally, the execution is strictly computationally bound. It underutilizes modern multi-core/SIMD capable architectures.

### 2.2 Lack of Strict Data Contracts
The ingestion generator trusts `count = int(count_str)` implicitly. Given production entropy, malformed strings or silently corrupt payloads (e.g., fractional sensors emitting `42.5` or `NaN`) will trigger unhandled exception bubbles or corrupt runtime memory scopes.

### 2.3 System Invariants and Path Dependencies
The script hardcodes `read_file_data("input.csv")`. Planetary-scale ingestion does not operate on local working directory assumptions. Implicit paths violate containerized scaling expectations (Docker/OCI/Kubernetes).

---

## 3. High-Tier Mitigation Strategies (No Implementation Provided)

To elevate this codebase to an enterprise-grade standard, the following optimization blueprints should be scheduled:

1. **Vectorization & Zero-Copy Execution** 
   - Abandon iterative `__next__` reading when possible in favor of **Polars** (`pl.scan_csv`) or **DuckDB**. 
   - Polars uses a lazy evaluation DAG backed by Apache Arrow. Calculations for min-contiguous windows (`rolling(*, window=3)`) and daily aggregations can be executed directly inside pre-compiled Rust multi-threaded kernels, skipping the GIL entirely and leveraging vector (SIMD) processing.

2. **Immutable Primitives Over Classes**
   - If vanilla Python *must* be maintained due to dependency limits, immediately replace `HalfHour` with native standard tuples (e.g., `tuple[int, float]`).
   - Tuple operations prevent `__dict__` and metadata allocation overhead. By hashing timestamps natively (`timestamp.timestamp()`) for sorting, `heapq` operates natively in contiguous C array contexts.

3. **Deque Implementation**
   - Replace the rolling array (`self._last_hour_and_half`) with a strictly sized `collections.deque(maxlen=3)`.
   - Appending to a `maxlen=3` deque natively drops the tail pointer with $\mathcal{O}(1)$ ring-buffer speed, entirely sidestepping consecutive array shifting over the CPU.

4. **Structured FTI Separation (Pydantic Integrity)**
   - All inbound stream elements must traverse a `Pydantic V2` data contract boundary handling type-coercion, nullable fields, bounds validation, and explicit UTC timezone synchronization before hitting the aggregation core.

5. **Parametrized Configuration**
   - Transition hardcoded I/O paths (e.g., `input.csv`) out of core execution layers in favor of `pydantic-settings` or simple command surface wrappers (`argparse`), decoupling the metrics domain logic from OS-level IO.
