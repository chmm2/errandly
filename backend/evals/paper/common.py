"""Shared plumbing for the paper experiments.

Everything under evals/paper imports the production modules unchanged. The
only things replaced are the places where production code talks to storage:
an AsyncSession is swapped for a small fake that hands back prepared rows, and
the Neo4j driver is pointed at a throwaway instance. The decision logic, the
constants and the Cypher are the ones the platform runs.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Results live in the repository's paper-artifacts folder, next to the exported
# datasets and run logs. Three levels up from here is the repository root on the
# host and "/" in the backend container, so the container needs the folder
# mounted at /paper-artifacts (see README.md); PAPER_RESULTS_DIR overrides both.
RESULTS_DIR = Path(
    os.environ.get("PAPER_RESULTS_DIR")
    or Path(__file__).resolve().parents[3] / "paper-artifacts" / "results"
)

# The driver logs an INFO line for every schema notice and planner hint. They
# are not errors and they drown the experiment output.
logging.getLogger("neo4j").setLevel(logging.WARNING)


def uid(i: int) -> str:
    """A stable UUID string for simulated student number i.

    find_rings() parses member ids with uuid.UUID, so simulated ids have to be
    real UUIDs rather than small integers.
    """
    return str(uuid.UUID(int=i + 1))


def hardware() -> dict:
    """CPU model, logical cores and memory visible to the process.

    The experiments run in a container, so these are the limits the container
    saw, which is what the timings were measured under."""
    info = {"logical_cpus": os.cpu_count()}
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                info["cpu"] = line.split(":", 1)[1].strip()
                break
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                info["mem_gib"] = round(int(line.split()[1]) / 1024**2, 1)
                break
    except OSError:
        info["cpu"] = platform.processor() or "unknown"
    return info


def save(name: str, data: dict) -> Path:
    """Write one experiment's results with enough metadata to reproduce it."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment": name,
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": os.environ.get("PAPER_GIT_COMMIT", "unknown"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "hardware": hardware(),
        "results": data,
    }
    path = RESULTS_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.seconds = time.perf_counter() - self.t0


class WarningCounter(logging.Handler):
    """Counts warnings from a production logger.

    run_read() swallows Neo4j failures by design and returns []. In production
    that is the safe direction; in an experiment it would silently turn an
    outage into "no rings found" and look like a recall result. Every graph
    experiment checks this counter and refuses to report if it moved.
    """

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.count = 0
        self.messages: list[str] = []

    def emit(self, record):
        self.count += 1
        detail = f" ({record.exc_info[1]!r})" if record.exc_info else ""
        self.messages.append(record.getMessage() + detail)


def attach_graph_warning_counter() -> WarningCounter:
    counter = WarningCounter()
    logging.getLogger("app.core.graph").addHandler(counter)
    return counter


def mean_sd(values: list[float]) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    m = sum(values) / len(values)
    if len(values) < 2:
        return m, 0.0
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return m, var**0.5


# Two-sided 95% Student t quantiles by degrees of freedom; beyond 30 the normal
# value is close enough for the intervals reported.
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
        15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        24: 2.064, 29: 2.045, 30: 2.042}


def ci95(values: list[float]) -> dict:
    """Mean, sample SD and the half-width of a t-based 95% interval."""
    m, s = mean_sd(values)
    n = len(values)
    if n < 2:
        return {"mean": m, "sd": 0.0, "ci": 0.0, "n": n}
    df = n - 1
    # Between tabulated values take the next smaller df, which is conservative.
    t = 1.96 if df > 30 else _T95[max(k for k in _T95 if k <= df)]
    return {"mean": m, "sd": s, "ci": t * s / n**0.5, "n": n}
