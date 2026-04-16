import marimo

__generated_with = "0.23.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import os
    import pstats
    import time

    import altair as alt
    import marimo as mo
    import polars as pl

    return alt, mo, os, pl, pstats, time


@app.cell
def _(alt, mo, os, pl, pstats):
    def load_prof_data(path, label=""):
        if not os.path.exists(path):
            path = "../../" + path
        if not os.path.exists(path):
            return pl.DataFrame()

        stats = pstats.Stats(path)
        data = []
        for func_tuple, metrics in stats.stats.items():
            filename = func_tuple[0].split("/")[-1] if "/" in func_tuple[0] else func_tuple[0]
            func_name = f"{filename}:{func_tuple[1]}({func_tuple[2]})"
            cc, nc, tt, ct, callers = metrics
            if nc > 0:
                data.append(
                    {
                        "Function": func_name,
                        "CumulativeTime": ct,
                        "TotalTime": tt,
                        "Calls": nc,
                        "TimePerCall": tt / nc if nc else 0,
                        "Variant": label,
                    }
                )
        return pl.DataFrame(data)

    df_base = load_prof_data("scratch/baseline.prof", "Baseline (Metrics)")
    df_opt = load_prof_data("scratch/optimized.prof", "StdLib (OptimizedMetrics)")

    if len(df_base) > 0 and len(df_opt) > 0:
        base_top = df_base.sort("CumulativeTime", descending=True).head(15)
        opt_top = df_opt.sort("CumulativeTime", descending=True).head(15)
        df_combined = pl.concat([base_top, opt_top])

        chart = (
            alt.Chart(df_combined)
            .mark_bar()
            .encode(
                x=alt.X("CumulativeTime:Q", title="Cumulative Time (s)"),
                y=alt.Y("Function:N", sort="-x", title="Function"),
                color="Variant:N",
                row=alt.Row("Variant:N", title=""),
            )
            .properties(
                title="Comparison: Top 15 Expensive Calls (Baseline vs Optimized StdLib)", width=600, height=200
            )
            .resolve_scale(y="independent")
        )
    else:
        chart = mo.md("Profiles not found.")
        df_combined = pl.DataFrame()

    return (chart,)


@app.cell
def _(mo, pl, time):
    start = time.time()
    try:
        # Theoretical lazy pipeline inside polars for Big-O benchmarking
        q = pl.scan_csv("scratch/large_input.csv", has_header=False, new_columns=["raw"])
        q = q.with_columns(pl.col("raw").str.split(by=" ").alias("split_col")).with_columns(
            [
                pl.col("split_col").list.first().str.to_datetime("%Y-%m-%dT%H:%M:%S").alias("timestamp"),
                pl.col("split_col").list.get(1).cast(pl.Int64).alias("count"),
            ]
        )
        res = q.select(["timestamp", "count"]).collect()
        polars_time = time.time() - start
    except Exception as e:
        polars_time = f"Error: {e}"
        res = None

    polars_md = mo.md(
        f"**Polars Execution Time (Read + Parse 500k rows):** `{polars_time if isinstance(polars_time, str) else f'{polars_time:.4f}s'}` (Raw C++ Multithreading)"
    )
    return (polars_md,)


@app.cell
def _(mo):
    summary_report = mo.md(
        """
        # 🏎️ Architectural Benchmark: FTI Pipeline Mitigations

        This reactive dashboard visualizes the specific performance deltas gathered by separating `Metrics` into an explicit `OptimizedMetrics` architecture inside `main.py` using **only the Python 3.x Standard Library.**

        """
    )

    technical_analysis = mo.vstack(
        [
            mo.md("## 1. Architectural Mitigations (Legacy vs Optimized)"),
            mo.callout(
                mo.md(
                    """
                ### 🔴 Memory GC Thrashing Eliminated (Space Complexity $\Downarrow$)
                The baseline spawned a heavy `HalfHour(count, timestamp)` Python dataclass per row. Over 500k rows, the Python allocator and garbage collector was forced to initialize and natively track half a million heavy Python structs with explicit `__dict__` bindings.
                
                **Fix:** Replaced explicit dataclass allocations entirely with strictly bound native primitive tuples `(count, timestamp)` bypassing implicit object instantiation loops.
                """
                ),
                kind="danger",
            ),
            mo.callout(
                mo.md(
                    """
                ### ⚠️ Contiguous C-Memory Heap Execution (Time Complexity $\Downarrow$)
                The legacy logic forced `heapq` (a highly optimized C-compiled pipeline bounds) to fall back entirely into the Python interpreter loop evaluating a custom `__lt__` (Less Than) dunder method across millions of priority swap resolutions.
                
                **Fix:** Eliminated the dunder methods entirely by leveraging float inversion to sort chronological dates mathematically: `(count, -timestamp.timestamp())`. The C-layer inherently calculates nested tuple indices seamlessly in contiguous memory.
                """
                ),
                kind="warn",
            ),
            mo.callout(
                mo.md(
                    """
                ### ✅ True $\mathcal{O}(1)$ Native Ring Buffers
                Tracking contiguous 1.5-hour sequence blocks natively relied on Python array indexing via `list.pop(0)`. Because dynamic arrays map to contiguous block spaces, slicing the leading index forces the interpreter to explicitly move all trailing variables sequentially left. 
                
                **Fix:** Exchanged standard sequences natively with `collections.deque(maxlen=3)`. Built as a linked-list implementation, hitting maximum limits organically terminates the tail-pointer reference in strict $\mathcal{O}(1)$ complexity.
                """
                ),
                kind="success",
            ),
            mo.md(
                """
            ## 2. Big-O Algorithmic Matrix & External Trajectory
            
            | Metric / Constraint | Baseline (`Metrics`) | StdLib (`OptimizedMetrics`) | External Polars (Rust / Arrow) |
            |---|---|---|---|
            | **Contiguous Storage** | $\mathcal{O}(M)$ (List Shift / `pop(0)`) | $\mathcal{O}(1)$ (`deque` Ring Buffer) | $\mathcal{O}(1)$ (Fast Agg Rolling) |
            | **Top K Peak Filter** | $\mathcal{O}(\log k)$ + Python Thread Block | $\mathcal{O}(\log k)$ Native C Layer | Vectorized Multi-Threaded Arrays |
            | **Memory GC Payload** | **Massive** (`dataclass` GC tracks) | **Minimal** (Primitive variables) | **Complete Offload** (Zero-copy memory) |
            
            ### Theoretical External Scaling Vector
            This notebook independently executes a simulation via `pl.scan_csv()` utilizing uninhibited multi-threaded Rust execution to definitively benchmark what external dependencies can achieve:
            """
            ),
        ]
    )
    return summary_report, technical_analysis


@app.cell
def _(chart, mo, polars_md, summary_report, technical_analysis):
    mo.vstack([summary_report, mo.ui.altair_chart(chart), mo.md("---"), technical_analysis, polars_md])
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
