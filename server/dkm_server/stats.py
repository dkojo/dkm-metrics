"""Statistics: per-variant summaries and variant-vs-control significance tests.

- Binary metrics (all values 0/1, e.g. thumbs_up, error): two-proportion z-test.
- Continuous metrics (latency, cost, ratings...): Welch's t-test.
"""

import math
from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats as sps

ALPHA = 0.05
POWER = 0.8
MIN_SAMPLES = 30  # per variant, before we'll call a result

LOWER_IS_BETTER = {"latency_ms", "cost", "tokens", "input_tokens", "output_tokens", "error"}


def lower_is_better(metric: str) -> bool:
    return metric in LOWER_IS_BETTER or metric.endswith(("_ms", "_cost", "_error", "_errors"))


@dataclass
class Summary:
    n: int
    mean: float
    std: float
    ci_low: float
    ci_high: float


@dataclass
class Comparison:
    test: str  # "proportion" | "welch_t"
    lift: float | None  # relative change vs control, e.g. 0.12 = +12%
    diff: float
    p_value: float | None
    significant: bool
    verdict: str  # "better" | "worse" | "no_difference" | "not_enough_data"
    samples_needed: int | None  # per variant, to detect the observed effect


def summarize(values: list[float]) -> Summary:
    a = np.asarray(values, dtype=float)
    n = len(a)
    if n == 0:
        return Summary(0, 0.0, 0.0, 0.0, 0.0)
    mean = float(a.mean())
    std = float(a.std(ddof=1)) if n > 1 else 0.0
    if n > 1:
        half = float(sps.t.ppf(1 - ALPHA / 2, n - 1)) * std / math.sqrt(n)
    else:
        half = 0.0
    return Summary(n, mean, std, mean - half, mean + half)


def is_binary(*samples: list[float]) -> bool:
    return all(v in (0.0, 1.0) for s in samples for v in s)


def _samples_needed(var_c: float, var_t: float, delta: float) -> int | None:
    if delta == 0:
        return None
    z = sps.norm.ppf(1 - ALPHA / 2) + sps.norm.ppf(POWER)
    return math.ceil(z**2 * (var_c + var_t) / delta**2)


def compare(control: list[float], treatment: list[float], metric: str) -> Comparison:
    c, t = np.asarray(control, dtype=float), np.asarray(treatment, dtype=float)
    mean_c = float(c.mean()) if len(c) else 0.0
    mean_t = float(t.mean()) if len(t) else 0.0
    diff = mean_t - mean_c
    lift = diff / abs(mean_c) if mean_c != 0 else None

    binary = is_binary(control, treatment)
    test = "proportion" if binary else "welch_t"

    if len(c) < 2 or len(t) < 2:
        return Comparison(test, lift, diff, None, False, "not_enough_data", None)

    if binary:
        pooled = (c.sum() + t.sum()) / (len(c) + len(t))
        se = math.sqrt(pooled * (1 - pooled) * (1 / len(c) + 1 / len(t)))
        p = float(2 * sps.norm.sf(abs(diff) / se)) if se > 0 else None
        var_c, var_t = mean_c * (1 - mean_c), mean_t * (1 - mean_t)
    else:
        var_c, var_t = float(c.var(ddof=1)), float(t.var(ddof=1))
        if var_c == 0 and var_t == 0:
            p = None
        else:
            p = float(sps.ttest_ind(t, c, equal_var=False).pvalue)

    if p is not None and math.isnan(p):
        p = None

    significant = p is not None and p < ALPHA
    if min(len(c), len(t)) < MIN_SAMPLES:
        verdict = "not_enough_data"
        significant = False
    elif significant:
        improved = diff < 0 if lower_is_better(metric) else diff > 0
        verdict = "better" if improved else "worse"
    else:
        verdict = "no_difference"

    needed = None if significant else _samples_needed(var_c, var_t, diff)
    return Comparison(test, lift, diff, p, significant, verdict, needed)


def analyze(metric: str, by_variant: dict[str, list[float]], control_key: str) -> dict:
    """Full result for one metric across all variants."""
    control = by_variant.get(control_key, [])
    variants = []
    for key, values in by_variant.items():
        row = {"variant": key, **asdict(summarize(values))}
        if key != control_key:
            row["comparison"] = asdict(compare(control, values, metric))
        variants.append(row)
    return {
        "metric": metric,
        "lower_is_better": lower_is_better(metric),
        "binary": is_binary(*by_variant.values()),
        "variants": variants,
    }
