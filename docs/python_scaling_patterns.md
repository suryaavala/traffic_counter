---
title: Python Scaling Patterns
marimo-version: 0.23.0
width: medium
---

```python {.marimo}
import marimo as mo
import time
import collections
import heapq
from dataclasses import dataclass
```

# 🏎️ Python Native Scaling: Visualizing Core Bottlenecks

This interactive notebook directly demonstrates the underlying hardware execution bounds governing pristine Python architectures:
1. **Array Memory Shifting** (`list.pop` vs `collections.deque`)
2. **Garbage Collection Thrashing** (`dataclass` vs Primitives)
3. **C-Extension Boundaries** (Custom context dunders vs Native C-bindings)

```python {.marimo}
array_slider = mo.ui.slider(
    start=100000,
    stop=2000000,
    step=100000,
    value=500000,
    label="Simulation Processing Matrix (N Actions): ",
)
```

```python {.marimo}
N = array_slider.value

# 1. Dynamic Array (List Shifting) Simulation
start = time.time()
dynamic_array = list(range(100))
for _ in range(N):
    dynamic_array.append(_)
    if len(dynamic_array) > 3:
        dynamic_array.pop(0)  # O(M) Sequential Shift
list_time = time.time() - start

# 2. Ring Buffer (Linked List) Simulation
start2 = time.time()
ring_buffer = collections.deque(range(100), maxlen=3)
for _ in range(N):
    ring_buffer.append(_)  # O(1) Tail clipping
deque_time = time.time() - start2

mo.md(
    f"""
    ## 1. Dynamic Array Shifting vs Linked Lists
    Adjust the slider to simulate tracking contiguous architectures logically shifting memory nodes during streaming limits:

    {array_slider}

    **`list.pop(0)` Execution (Contiguous Sequence Left Shift $\mathcal{{O}}(M)$)**
    - Time: `{list_time:.5f}s` 🔴 (Degrades exponentially as internal arrays scale due to forced memory realignment)

    **`collections.deque(maxlen=3)` (Ring Buffer Tail Truncation $\mathcal{{O}}(1)$)**
    - Time: `{deque_time:.5f}s` ✅ (Near-instant execution universally utilizing doubly-linked physical node truncation)
    """
)
```

```python {.marimo}
@dataclass
class HeavyObject:
    count: int

    def __lt__(self, other):
        return self.count < other.count

# 1. Object Initialization & Heap Fallback
start_obj = time.time()
heap_obj = []
# Intentionally bottlenecking GC loops
for i in range(N):
    item = HeavyObject(count=i)
    heapq.heappush(heap_obj, item)
obj_time = time.time() - start_obj

# 2. Primitive Execution & Native C-Heap
start_prim = time.time()
heap_prim = []
for i in range(N):
    item = (i,)
    heapq.heappush(heap_prim, item)
prim_time = time.time() - start_prim

mo.md(
    f"""
    ---
    ## 2. Object Instantiation GC & C-Memory Context Boundaries
    Instantiating python classes forces tracking via explicit metadata `__dict__` bindings across the interpreter Garbage Collector. Native tuples inherently sidestep this GC check perfectly.

    Additionally, executing `heapq` normally natively anchors priority swaps securely within low-tier **C-Extensions**. But invoking a custom Python `__lt__` forces the C-compiled module to continuously halt entirely over thousands of loops to call out into the slower Python Interpreter!

    Tracking `N={N:,}` Active Elements:

    **Python Interpreter Yielding (Python Object + `__lt__`)**
    - Time: `{obj_time:.5f}s` 🔴 (Yield penalties and GC Tracking severely degrades large ingestion loops)

    **C-Nativization Context Limits (Raw primitives + inherent structs)**
    - Time: `{prim_time:.5f}s` ✅ (Executed efficiently inside low-level C with strict Zero-alloc structures)
    """
)
```