#!/usr/bin/env python3
"""
ピアノードの入出力モデルが正しく実装されているかを、実際の解で検証する。

確認する4点:
  (1) ミキサーサイズ = 入力単位数。1:1なら2、1:2なら3 になっているか。
  (2) 出力エッジは最大でミキサーサイズ分か。
  (3) 出力エッジの重み(供給量)が、ミキサーサイズ3以上で1や2になっているか。
  (4) 廃棄計算が、1:1でないとき正しいか(廃棄 = ミキサーサイズ - 使われた量)。

ピアが使われた解を解き、各ピアについて
  入力消費(from_a, from_b)、出力先と各エッジの量、廃棄
を取り出して、つじつまが合うか検算する。

使い方:
  python3 verify_peer.py --targets "10,39,23/4,3,3,2;13,15,8/4,3,3" --time 60
"""
import io
import argparse
import contextlib

from utils.config_loader import Config
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.model.problem import MTWMProblem
from core.solver.engine import OrToolsSolver


def parse_targets(s):
    targets = []
    for i, part in enumerate(s.split(";")):
        ratio_str, factor_str = part.split("/")
        targets.append({
            "name": f"T{i}",
            "ratios": [int(x) for x in ratio_str.split(",")],
            "factors": [int(x) for x in factor_str.split(",")],
        })
    return targets


def main():
    ap = argparse.ArgumentParser(description="ピアノードの入出力検証")
    ap.add_argument("--targets", type=str, required=True)
    ap.add_argument("--time", type=float, default=60.0)
    args = ap.parse_args()

    targets = parse_targets(args.targets)
    Config.PEER_NODE_LIMIT = "half_p_group"
    Config.ENABLE_HETERO_PEER = True
    Config.HETERO_RATIOS = "1:1,2:1,1:2"
    Config.HETERO_MULTIPLE_ONLY = True
    Config.MAX_LEVEL_DIFF = None

    forest = build_dfmm_forest(targets)
    pmaps = calculate_p_values_from_structure(forest, targets)
    with contextlib.redirect_stdout(io.StringIO()):
        prob = MTWMProblem(targets, forest, pmaps)
        solver = OrToolsSolver(prob, objective_mode="waste")
        solver.solver.parameters.log_search_progress = False
        solver.solver.parameters.max_time_in_seconds = args.time
        _m, _v, a, _t = solver.solve()

    if a is None:
        print("解なし")
        return
    status = a.get("solver_status", "?")
    print("=" * 64)
    print(f"  ピアノード入出力検証  (nw={a['total_waste']}, {status})")
    print("=" * 64)
    if status != "OPTIMAL":
        print("  ★警告: 非OPTIMAL。検証結果は参考値。--time を増やすこと。\n")

    sv = solver.solver
    any_used = False
    for i, peer in enumerate(solver.peer_vars):
        if peer.get("is_generic"):
            continue
        if not sv.Value(peer["is_active_var"]):
            continue
        any_used = True
        is_hetero = peer.get("is_hetero", False)
        ra = peer.get("ratio_a", 1)
        rb = peer.get("ratio_b", 1)
        wa = peer.get("weight_a", "?")
        wb = peer.get("weight_b", "?")
        p_new = peer["p_value"]

        # 入力消費
        from_a = sv.Value(peer["input_vars"]["from_a"]) if "from_a" in peer.get("input_vars", {}) else "?"
        from_b = sv.Value(peer["input_vars"]["from_b"]) if "from_b" in peer.get("input_vars", {}) else "?"
        total_input = sv.Value(peer["total_input_var"])
        waste = sv.Value(peer["waste_var"])

        # 出力先(このピアを使っているノードと、その量)
        outgoing = solver._get_outgoing_vars_from_peer(i)
        out_amounts = [sv.Value(v) for v in outgoing]
        total_used = sum(out_amounts)
        n_edges = sum(1 for x in out_amounts if x > 0)

        print(f"\n  ピア {peer['name']}")
        print(f"    種別: {'異重き' if is_hetero else '等重き'}, "
              f"入力重み {wa}×{wb}, 体積比 {ra}:{rb}, 出力重み {p_new}")
        # (1) ミキサーサイズ
        expected_size = (ra + rb) if is_hetero else 2
        ms_ok = (total_input == expected_size)
        print(f"    (1) ミキサーサイズ: 入力消費 from_a={from_a}, from_b={from_b}, "
              f"合計={total_input} (期待={expected_size}) {'OK' if ms_ok else '★不一致'}")
        # (2)(3) 出力エッジ
        print(f"    (2) 出力エッジ数: {n_edges} (最大={expected_size}) "
              f"{'OK' if n_edges <= expected_size else '★超過'}")
        print(f"    (3) 各エッジの量(重み): {[x for x in out_amounts if x > 0]}")
        # (4) 廃棄
        waste_calc = total_input - total_used
        w_ok = (waste == waste_calc and waste >= 0)
        print(f"    (4) 廃棄: total_prod={total_input} - total_used={total_used} "
              f"= {waste_calc}, 記録waste={waste} {'OK' if w_ok else '★不一致'}")

    if not any_used:
        print("\n  異重き/固定ピアは使われていない。")
    print("=" * 64)


if __name__ == "__main__":
    main()