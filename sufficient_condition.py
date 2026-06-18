#!/usr/bin/env python3
"""
案Aの深掘り: 「同一ツリー内ペアは必要条件だが十分条件でない。では何が十分条件か」
を探るための詳細特徴分析。

condition_analysis.py より多くの構造特徴を抽出し、効く/効かないを分ける
追加要因を探す。特に「同一ツリー内ペアを持つケース」に絞って、その中で
効く/効かないを分ける特徴を見る(=十分条件の探索)。

抽出する追加特徴:
  - max_mult_ratio: 倍数ペアの倍率の最大(18と6なら3)。大きいほど軽い出力が作れる
  - n_deep_trees: 4段以上の深いツリーの数
  - min_leaf_weight: 最小のleaf重み(軽い液滴の必要性)
  - same_tree_pair_with_light: 同一ツリー内ペアで軽い出力(<=2)が作れるものの数

使い方:
  python3 sufficient_condition.py --cases 300 --time 120 --targets 2 --sums 54,72
出力(suff_results/):
  summary.txt, cases_raw.csv, charts
"""
import io
import os
import time
import argparse
import contextlib
import statistics
from collections import defaultdict
from math import gcd, lcm
from functools import reduce

from utils.config_loader import Config
from core.generator import RandomScenarioGenerator
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.model.problem import MTWMProblem
from core.solver.engine import OrToolsSolver
from bench_output import save_summary, draw_bar_chart, save_csv


def solve_waste(targets, hetero, time_limit):
    Config.PEER_NODE_LIMIT = "half_p_group"
    Config.ENABLE_HETERO_PEER = hetero
    Config.HETERO_RATIOS = "1:1,2:1,1:2"
    Config.HETERO_MULTIPLE_ONLY = True
    Config.MAX_LEVEL_DIFF = None
    try:
        forest = build_dfmm_forest(targets)
        pmaps = calculate_p_values_from_structure(forest, targets)
        with contextlib.redirect_stdout(io.StringIO()):
            prob = MTWMProblem(targets, forest, pmaps)
            solver = OrToolsSolver(prob, objective_mode="waste")
            solver.solver.parameters.log_search_progress = False
            solver.solver.parameters.max_time_in_seconds = time_limit
            _m, _v, a, _t = solver.solve()
        if a is None:
            return None, None
        return a["total_waste"], a.get("solver_status", "?")
    except Exception:
        return None, None


def extract_detailed_features(targets):
    """十分条件を探るための詳細な構造特徴を抽出。"""
    forest = build_dfmm_forest(targets)
    pmaps = calculate_p_values_from_structure(targets and forest, targets)
    weight_loc = defaultdict(list)
    for ti, tree in enumerate(forest):
        for (lvl, k) in tree.keys():
            if lvl == 0:
                continue
            p = pmaps[ti][(lvl, k)]
            f = targets[ti]["factors"][lvl]
            if p != f:
                weight_loc[p].append((ti, lvl))
    ws = sorted(weight_loc.keys())

    same_tree_mult = 0
    cross_tree_mult = 0
    max_mult_ratio = 0
    same_tree_light = 0  # 同一ツリー内ペアで軽い出力(<=2)が作れる数
    for i, a in enumerate(ws):
        for b in ws[i + 1:]:
            hi, lo = max(a, b), min(a, b)
            if hi % lo != 0:
                continue
            ratio = hi // lo
            for (ta, _la) in weight_loc[a]:
                for (tb, _lb) in weight_loc[b]:
                    if ta == tb:
                        same_tree_mult += 1
                        max_mult_ratio = max(max_mult_ratio, ratio)
                        # 軽い出力が作れるか(簡易: lo<=2 ならleaf級の軽さ)
                        if lo <= 6:  # 重み6以下のペアは軽い出力を作りやすい
                            same_tree_light += 1
                    else:
                        cross_tree_mult += 1

    depths = [len(t["factors"]) for t in targets]
    return {
        "multi_depth": len(set(depths)) > 1,
        "n_weight_types": len(ws),
        "same_tree_mult": same_tree_mult,
        "cross_tree_mult": cross_tree_mult,
        "max_mult_ratio": max_mult_ratio,
        "same_tree_light": same_tree_light,
        "n_deep_trees": sum(1 for d in depths if d >= 4),
        "max_depth": max(depths),
    }


def main():
    ap = argparse.ArgumentParser(description="十分条件の探索: 効く/効かないを分ける追加要因")
    ap.add_argument("--cases", type=int, default=300)
    ap.add_argument("--time", type=float, default=120.0)
    ap.add_argument("--reagents", type=int, default=3)
    ap.add_argument("--targets", type=int, default=2)
    ap.add_argument("--sums", type=str, default="54,72",
                    help="総和候補。深い4段(54,72,108)推奨。同一ツリー内ペアを出すため。")
    args = ap.parse_args()

    Config.RANDOM_T_REAGENTS = args.reagents
    Config.RANDOM_N_TARGETS = args.targets
    Config.RANDOM_S_RATIO_SUM_CANDIDATES = [int(s) for s in args.sums.split(",")]
    Config.RANDOM_S_RATIO_SUM_SEQUENCE = []
    Config.RANDOM_K_RUNS = args.cases

    gen = RandomScenarioGenerator(Config)
    scenarios = gen.generate_batch_configs(args.cases)
    print(f"生成: {len(scenarios)}ケース (総和候補={Config.RANDOM_S_RATIO_SUM_CANDIDATES})")

    improved = []
    not_improved = []
    # 同一ツリー内ペアを持つケースだけの中で効く/効かない(=十分条件の探索)
    with_pair_improved = []
    with_pair_not = []
    non_optimal = 0
    tested = 0
    case_rows = []

    for rc in scenarios:
        targets = rc["targets"]
        wt, st = solve_waste(targets, False, args.time)
        wp, sp = solve_waste(targets, True, args.time)
        if wt is None or wp is None:
            continue
        tested += 1
        is_opt = (st == "OPTIMAL" and sp == "OPTIMAL")
        if not is_opt:
            non_optimal += 1
        feat = extract_detailed_features(targets)
        imp = wp < wt
        feat["reduction"] = wt - wp
        case_rows.append([
            rc.get("run_name", ""),
            ";".join(str(t["ratios"]) for t in targets),
            ";".join(str(t["factors"]) for t in targets),
            wt, wp, wt - wp,
            int(feat["multi_depth"]), feat["n_weight_types"],
            feat["same_tree_mult"], feat["cross_tree_mult"],
            feat["max_mult_ratio"], feat["same_tree_light"],
            feat["n_deep_trees"], feat["max_depth"],
            int(imp), st, sp,
        ])
        # ★時間切れケースは十分条件分析から除外(偽結果を排除)
        if not is_opt:
            continue
        (improved if imp else not_improved).append(feat)
        if feat["same_tree_mult"] > 0:
            (with_pair_improved if imp else with_pair_not).append(feat)

    if tested == 0:
        print("有効ケースなし")
        return

    def stat(feats, key):
        return statistics.mean(f[key] for f in feats) if feats else 0

    print(f"\n{'='*64}")
    print(f"  十分条件の探索 [{tested}ケース, 時間切れ{100*non_optimal/tested:.0f}%]")
    print(f"  ※時間切れケースは十分条件分析から除外済み")
    print(f"{'='*64}")
    print(f"  OPTIMAL確定: 効いた{len(improved)}件 / 効かない{len(not_improved)}件\n")

    # ★核心: 同一ツリー内ペアを「持つ」ケースに絞って、効く/効かないを分ける特徴
    print(f"  ★同一ツリー内ペアを持つケースの中での比較(=十分条件の探索)")
    print(f"    効いた{len(with_pair_improved)}件 vs 効かない{len(with_pair_not)}件")
    for key, label in [("max_mult_ratio", "倍数ペアの最大倍率"),
                       ("same_tree_light", "軽い出力可の同一ツリー内ペア数"),
                       ("n_deep_trees", "深いツリー(4段+)の数"),
                       ("max_depth", "最大深さ"),
                       ("n_weight_types", "重み種類数"),
                       ("cross_tree_mult", "ツリー間ペア数")]:
        vi = stat(with_pair_improved, key)
        vn = stat(with_pair_not, key)
        diff = "←差あり" if abs(vi - vn) > 0.3 else ""
        print(f"    {label:<28}: 効いた{vi:.2f} vs 効かない{vn:.2f} {diff}")
    print(f"{'='*64}\n")

    # 出力
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("suff_results", f"suff_{ts}")
    os.makedirs(out_dir, exist_ok=True)
    save_csv(os.path.join(out_dir, "cases_raw.csv"),
             ["run_name", "ratios", "factors", "nw_thesis", "nw_proposed", "reduction",
              "multi_depth", "n_weight_types", "same_tree_mult", "cross_tree_mult",
              "max_mult_ratio", "same_tree_light", "n_deep_trees", "max_depth",
              "improved", "status_thesis", "status_proposed"],
             case_rows)
    # 十分条件候補の比較グラフ
    if with_pair_improved and with_pair_not:
        keys = ["max_mult_ratio", "same_tree_light", "n_deep_trees", "max_depth"]
        labels = ["max_mult_ratio", "same_tree_light", "n_deep_trees", "max_depth"]
        vi = [stat(with_pair_improved, k) for k in keys]
        vn = [stat(with_pair_not, k) for k in keys]
        draw_bar_chart(labels, [vi, vn],
                       os.path.join(out_dir, "sufficient_condition.png"),
                       title="Features: improved vs not (among cases with same-tree pair)",
                       ylabel="Average value",
                       legend=["improved", "not improved"])
    rows = [
        ["効いた(同一ツリー内ペアあり)", len(with_pair_improved),
         f"{stat(with_pair_improved,'max_mult_ratio'):.2f}",
         f"{stat(with_pair_improved,'n_deep_trees'):.2f}",
         f"{stat(with_pair_improved,'max_depth'):.2f}"],
        ["効かない(同一ツリー内ペアあり)", len(with_pair_not),
         f"{stat(with_pair_not,'max_mult_ratio'):.2f}",
         f"{stat(with_pair_not,'n_deep_trees'):.2f}",
         f"{stat(with_pair_not,'max_depth'):.2f}"],
    ]
    save_summary(os.path.join(out_dir, "summary.txt"),
                 ["分類", "件数", "最大倍率", "深いツリー数", "最大深さ"], rows,
                 [f"時間切れ{100*non_optimal/tested:.0f}%(分析から除外済)",
                  "同一ツリー内ペアを持つケースに絞り、効く/効かないを分ける特徴を探す。",
                  "差のある特徴が十分条件の候補。"])
    print(f"要約: {out_dir}/summary.txt")
    print(f"生データCSV: {out_dir}/cases_raw.csv")
    print(f"グラフ: {out_dir}/sufficient_condition.png")


if __name__ == "__main__":
    main()