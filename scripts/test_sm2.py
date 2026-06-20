"""SM-2 间隔重复算法测试。

覆盖：interval 递推、ease 衰减、quality 各档位边界、
连续多次复习序列、must_know 严格评分。
"""

import sys
sys.path.insert(0, r"C:\Users\qiyong\.agents\skills\cram-engine\scripts")
from utils import sm2_update, sm2_quality_from_accuracy


def test_initial_state():
    sm2 = {"interval": 0, "ease": 2.5, "repetitions": 0, "next_review": None}
    assert sm2["interval"] == 0
    assert sm2["ease"] == 2.5
    assert sm2["repetitions"] == 0
    print("PASS test_initial_state")


def test_perfect_sequence():
    sm2 = {"interval": 0, "ease": 2.5, "repetitions": 0, "next_review": None}
    intervals = []
    for _ in range(5):
        sm2 = sm2_update(sm2, 5)
        intervals.append(sm2["interval"])
    assert intervals[0] == 1, f"R1 interval should be 1, got {intervals[0]}"
    assert intervals[1] == 6, f"R2 interval should be 6, got {intervals[1]}"
    assert intervals[2] >= 14, f"R3 interval should be >=14, got {intervals[2]}"
    assert intervals[3] > intervals[2], "Interval should increase"
    assert intervals[4] > intervals[3], "Interval should increase"
    assert sm2["repetitions"] == 5
    assert sm2["ease"] >= 2.9, f"Ease should grow: {sm2['ease']}"
    print("PASS test_perfect_sequence")


def test_forgot_reset():
    sm2 = {"interval": 0, "ease": 2.5, "repetitions": 0, "next_review": None}
    for _ in range(3):
        sm2 = sm2_update(sm2, 5)
    assert sm2["repetitions"] == 3
    sm2 = sm2_update(sm2, 1)
    assert sm2["repetitions"] == 0, f"Reps should reset: {sm2['repetitions']}"
    assert sm2["interval"] == 1, f"Interval should reset: {sm2['interval']}"
    assert sm2["ease"] < 2.5, f"Ease should drop: {sm2['ease']}"
    print("PASS test_forgot_reset")


def test_ease_never_below_1_3():
    sm2 = {"interval": 0, "ease": 1.3, "repetitions": 0, "next_review": None}
    for _ in range(10):
        sm2 = sm2_update(sm2, 0)
    assert sm2["ease"] >= 1.3, f"Ease floor: {sm2['ease']}"
    print("PASS test_ease_never_below_1_3")


def test_quality_below_3_resets():
    sm2 = {"interval": 0, "ease": 2.5, "repetitions": 0, "next_review": None}
    sm2 = sm2_update(sm2, 5)
    sm2 = sm2_update(sm2, 5)
    assert sm2["interval"] == 6
    sm2 = sm2_update(sm2, 2)
    assert sm2["repetitions"] == 0
    assert sm2["interval"] == 1
    print("PASS test_quality_below_3_resets")


def test_must_know_strict():
    # 2/3 = 67%：must_know < 80% -> quality=2, 普通 >= 50% -> quality=3
    assert sm2_quality_from_accuracy(2, 3, True) == 2
    assert sm2_quality_from_accuracy(2, 3, False) == 3
    # 3/4 = 75%：must_know < 80% -> quality=2, 普通 >= 75% -> quality=4
    assert sm2_quality_from_accuracy(3, 4, True) == 2
    assert sm2_quality_from_accuracy(3, 4, False) == 4
    # 4/5 = 80%：must_know >= 80% -> quality=3
    assert sm2_quality_from_accuracy(4, 5, True) == 3
    print("PASS test_must_know_strict")


def test_edge_quality():
    assert sm2_quality_from_accuracy(0, 0, True) == 3
    assert sm2_quality_from_accuracy(1, 1, True) == 5
    assert sm2_quality_from_accuracy(0, 3, True) == 1
    assert sm2_quality_from_accuracy(0, 3, False) == 1
    print("PASS test_edge_quality")


def test_next_review_date_format():
    import re
    sm2 = sm2_update({"interval": 0, "ease": 2.5, "repetitions": 0, "next_review": None}, 5)
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", sm2["next_review"]), \
        f"Bad date: {sm2['next_review']}"
    print("PASS test_next_review_date_format")


def test_custom_review_date():
    sm2 = {"interval": 0, "ease": 2.5, "repetitions": 0, "next_review": None}
    sm2 = sm2_update(sm2, 5, review_date="2026-01-01")
    assert sm2["next_review"] == "2026-01-02"
    print("PASS test_custom_review_date")


if __name__ == "__main__":
    tests = [
        test_initial_state,
        test_perfect_sequence,
        test_forgot_reset,
        test_ease_never_below_1_3,
        test_quality_below_3_resets,
        test_must_know_strict,
        test_edge_quality,
        test_next_review_date_format,
        test_custom_review_date,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
    assert passed == len(tests), f"{len(tests) - passed} tests failed"
