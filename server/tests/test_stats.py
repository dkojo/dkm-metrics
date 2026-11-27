import random

from dkm_server import stats


def test_summarize():
    s = stats.summarize([1, 2, 3, 4, 5])
    assert s.n == 5 and s.mean == 3
    assert s.ci_low < 3 < s.ci_high
    assert stats.summarize([]).n == 0


def test_not_enough_data():
    c = stats.compare([0, 1, 1], [1, 1, 1], "thumbs_up")
    assert c.verdict == "not_enough_data" and not c.significant


def test_lower_is_better_direction():
    rng = random.Random(1)
    control = [rng.gauss(1000, 50) for _ in range(200)]
    faster = [rng.gauss(700, 50) for _ in range(200)]
    c = stats.compare(control, faster, "latency_ms")
    assert c.verdict == "better"
    c = stats.compare(faster, control, "latency_ms")
    assert c.verdict == "worse"


def test_no_difference():
    rng = random.Random(2)
    a = [rng.gauss(5, 1) for _ in range(100)]
    b = [x + 0.01 for x in reversed(a)]  # same distribution, tiny real difference
    c = stats.compare(a, b, "rating")
    assert c.verdict == "no_difference"
    assert c.samples_needed is not None


def test_zero_variance_is_safe():
    c = stats.compare([1.0] * 50, [1.0] * 50, "rating")
    assert c.p_value is None and c.verdict == "no_difference"
