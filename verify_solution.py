#!/usr/bin/env python3
"""
実行結果の検証ツール: 特定のケースを指定し、解が正しく構成されているかを確認する。

CSVで「効いた」とされたケースなどを、十分な時間をかけて解き直し、
  - 解が OPTIMAL に到達したか（時間切れの偽結果でないか）
  - 異重きピアが同一ツリー内かツリー間か、何を混ぜたか
  - 解の木の画像と、各ノードの混合内容
を出力する。これにより「本当に効いているか」を目で検証できる。

使い方（ターゲットを直接指定）:
  python3 verify_solution.py --targets "39,10,5/3,3,3,2;34,31,7/4,3,3,2;31,2,3/4,3,3" --time 300

  --targets 形式: "比1/factors1;比2/factors2;..."
    各ターゲットは 比(カンマ区切り)/factors(カンマ区切り) を ; で連結。
  --time: ソルバー時間（OPTIMAL到達のため十分長く。300〜600推奨）
"""
import io
import os
import time
import argparse
import contextlib

from utils.config_loader import Config
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.model.problem import MTWMProblem
from core.solver.engine import OrToolsSolver
from bench_output import draw_solution_tree, save_solution_detail


def parse_targets(s):
    targets = []
    for i, part in enumerate(s.split(";")):
        ratio_str, factor_str = part.split("/")
        ratios = [int(x) for x in ratio_str.split(",")]
        factors = [int(x) for x in factor_str.split(",")]
        targets.append({"name": f"T{i}", "ratios": ratios, "factors": factors})
    return targets


def solve_and_report(targets, hetero, time_limit, label):
    Config.PEER_NODE_LIMIT = "half_p_group"
    Config.ENABLE_HETERO_PEER = hetero
    Config.HETERO_RATIOS = "1:1,2:1,1:2"
    Config.HETERO_MULTIPLE_ONLY = True
    Config.MAX_LEVEL_DIFF = None
    forest = build_dfmm_forest(targets)
    pmaps = calculate_p_values_from_structure(forest, targets)
    with contextlib.redirect_stdout(io.StringIO()):
        prob = MTWMProblem(targets, forest, pmaps)
        solver = OrToolsSolver(prob, objective_mode="waste")
        solver.solver.parameters.log_search_progress = False
        solver.solver.parameters.max_time_in_seconds = time_limit
        _m, _v, a, _t = solver.solve()
    if a is None:
        print(f"  [{label}] 解なし")
        return None, None, []
    status = a.get("solver_status", "?")
    waste = a["total_waste"]
    # 使われた異重きピア
    used = []
    if hetero:
        for pn in solver.peer_vars:
            if pn.get("is_hetero") and solver.solver.Value(pn["is_active_var"]):
                sa = pn.get("source_a_id")
                sb = pn.get("source_b_id")
                same = (sa[0] == sb[0])
                used.append({
                    "same_tree": same,
                    "weight_a": pn.get("weight_a"),
                    "weight_b": pn.get("weight_b"),
                    "ratio_a": pn.get("ratio_a", 1),
                    "ratio_b": pn.get("ratio_b", 1),
                    "p_value": pn.get("p_value"),
                })
    return waste, status, used, a


def main():
    ap = argparse.ArgumentParser(description="解の検証ツール")
    ap.add_argument("--targets", type=str, required=True,
                    help='"比/factors;比/factors;..." 形式')
    ap.add_argument("--time", type=float, default=300.0, help="ソルバー時間(秒)")
    args = ap.parse_args()

    targets = parse_targets(args.targets)
    print("=" * 64)
    print("  解の検証")
    print("=" * 64)
    for t in targets:
        print(f"  {t['name']}: 比{t['ratios']} factors={t['factors']}")
    print(f"  ソルバー時間: {args.time}秒")
    print("=" * 64)

    # 卒論(異重きなし)と提案(異重きあり)を両方解く
    wt, st, _, _ = solve_and_report(targets, False, args.time, "卒論")
    wp, sp, used, a_prop = solve_and_report(targets, True, args.time, "提案")

    print(f"\n  卒論(等重きのみ): nw={wt} ({st})")
    print(f"  提案(異重きあり): nw={wp} ({sp})")
    print()

    # ★信頼性の判定
    if st != "OPTIMAL" or sp != "OPTIMAL":
        print("  ★警告: どちらかが時間切れ(非OPTIMAL)。この結果は信頼できない。")
        print("    --time を増やして再実行すること。")
    else:
        print("  ★両方OPTIMAL = この結果は信頼できる。")
        if wp < wt:
            print(f"    → 提案が {wt-wp} 個削減(確実な改善)。")
        elif wp == wt:
            print(f"    → 提案と卒論が同じ(異重きの効果なし、このケースでは)。")
        else:
            print(f"    → 提案が悪化?!(最適同士なら起きないはず。要調査)")

    # 使われた異重きピア
    if used:
        print(f"\n  使われた異重きピア({len(used)}個):")
        same_n = sum(1 for u in used if u["same_tree"])
        cross_n = len(used) - same_n
        print(f"    同一ツリー内: {same_n}個, ツリー間: {cross_n}個")
        for u in used:
            loc = "同一ツリー" if u["same_tree"] else "ツリー間"
            print(f"    [{loc}] 重み{u['weight_a']}×{u['weight_b']} "
                  f"体積比{u['ratio_a']}:{u['ratio_b']} → 出力重み{u['p_value']}")
    else:
        print("\n  異重きピアは使われていない。")

    # 解の木と詳細を保存
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("verify_results", f"verify_{ts}")
    os.makedirs(out_dir, exist_ok=True)
    if a_prop is not None:
        tree_png = os.path.join(out_dir, "solution_tree.png")
        ok = draw_solution_tree(a_prop, tree_png,
                                title=f"proposed nw={wp} ({sp})")
        detail = os.path.join(out_dir, "solution_detail.txt")
        save_solution_detail(detail, a_prop, label="検証対象(提案)")
        print(f"\n  解の木: {tree_png}")
        print(f"  解の詳細: {detail}")
    print("=" * 64)


if __name__ == "__main__":
    main()