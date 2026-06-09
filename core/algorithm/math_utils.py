import random
import math
from functools import reduce

def _calculate_gcd_for_list(numbers):
    """リスト内のすべての数値の最大公約数（GCD）を計算します。"""
    if not numbers:
        return 1
    return reduce(math.gcd, numbers)

def generate_random_ratios(reagent_count, ratio_sum, max_retries=100):
    """
    指定された合計値(ratio_sum)になる、指定個数(reagent_count)の
    0を含まないランダムな整数のリストを生成します (GCD=1)。
    """
    if ratio_sum < reagent_count:
        raise ValueError(
            f"Ratio sum ({ratio_sum}) cannot be less than the number of reagents ({reagent_count})."
        )

    for _ in range(max_retries):
        # 1〜(ratio_sum-1) の範囲から仕切りを選ぶ
        dividers = sorted(random.sample(range(1, ratio_sum), reagent_count - 1))
        ratios = []
        last_divider = 0
        
        for d in dividers:
            ratios.append(d - last_divider)
            last_divider = d
        ratios.append(ratio_sum - last_divider)

        if _calculate_gcd_for_list(ratios) == 1:
            return ratios

    raise ValueError(
        f"Could not find a set of ratios with GCD=1 for sum {ratio_sum} after {max_retries} attempts."
    )