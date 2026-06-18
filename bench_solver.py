#!/usr/bin/env python3
"""
ソルバーパラメータが「最適性証明の速度」に与える効果を比較するベンチマーク。

最適解(nw)は変えず、証明にかかる時間だけを比較する。
各パラメータ設定について、同じ問題群を解き、
  - nw(最適解): 全設定で一致するはず(一致しなければ警告)
  - 状態(OPTIMAL/FEASIBLE): OPTIMAL=証明完了, FEASIBLE=時間切れ
  - 実時間
を表示する。

使い方（こちらの環境で実行）:
  python3 bench_solver.py                          # デフォルト設定で
  python3 bench_solver.py --sum 36 --reagents 4 --targets 3 --cases 5 --time 300
  python3 bench_solver.py --sum 135 --reagents 4 --targets 4 --cases 3 --time 3600

引数:
  --sum       成分比率の合計(例 36, 135)
  --reagents  試薬の種類数 t
  --targets   作る液滴数 μ
  --cases     テストケース数
  --time      1ケース1設定あたりのソルバー時間上限(秒)
  --seed      乱数シード
  --peer      ピアを使うか(off=従来MTWM, on=提案)。デフォルト off
"""
import io
import os
import time
import argparse
import contextlib

from utils.config_loader import Config
from core.generator import RandomScenarioGenerator
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.model.problem import MTWMProblem
from core.solver.engine import OrToolsSolver
from bench_output import save_summary, draw_solution_tree, save_solution_detail


# 比較するパラメータ設定。名前 -> ソルバーparametersを上書きする関数。
# 解の最適性は変えず、探索/証明の戦略だけ変える設定のみを並べる。
PARAM_SETS = {
    "baseline": lambda sp: None,
    "sym=2": lambda sp: setattr(sp, "symmetry_level", 2),
    "lin=2": lambda sp: setattr(sp, "linearization_level", 2),
    "sym2+lin2": lambda sp: (setattr(sp, "symmetry_level", 2),
                             setattr(sp, "linearization_level", 2)),
    "core=on": lambda sp: setattr(sp, "optimize_with_core", True),
    "probe": lambda sp: setattr(sp, "cp_model_probing_level", 2),
}


def solve_with(targets, param_fn, time_limit, use_peer):
    """1ケースを1パラメータ設定で解く。(nw, status, elapsed, analysis) を返す。"""
    if use_peer:
        Config.PEER_NODE_LIMIT = "half_p_group"
        Config.ENABLE_HETERO_PEER = True
    else:
        Config.PEER_NODE_LIMIT = 0
        Config.ENABLE_HETERO_PEER = False
    forest = build_dfmm_forest(targets)
    pmaps = calculate_p_values_from_structure(forest, targets)
    with contextlib.redirect_stdout(io.StringIO()):
        prob = MTWMProblem(targets, forest, pmaps)
        solver = OrToolsSolver(prob, objective_mode="waste")
        sp = solver.solver.parameters
        sp.log_search_progress = False
        sp.max_time_in_seconds = time_limit
        param_fn(sp)  # パラメータ上書き
        t0 = time.time()
        _m, _v, a, _t = solver.solve()
        elapsed = time.time() - t0
    if a is None:
        return None, "なし", elapsed, None
    return a["total_waste"], a.get("solver_status", "?"), elapsed, a


def main():
    ap = argparse.ArgumentParser(description="ソルバーパラメータの証明速度ベンチマーク")
    ap.add_argument("--sum", type=int, default=36, help="成分比率の合計")
    ap.add_argument("--reagents", type=int, default=3, help="試薬の種類数 t")
    ap.add_argument("--targets", type=int, default=3, help="作る液滴数 μ")
    ap.add_argument("--cases", type=int, default=3, help="テストケース数")
    ap.add_argument("--time", type=float, default=120.0, help="1ケース1設定の時間上限(秒)")
    ap.add_argument("--seed", type=int, default=42, help="乱数シード")
    ap.add_argument("--peer", choices=["off", "on"], default="off",
                    help="ピア使用(off=従来MTWM, on=提案)")
    args = ap.parse_args()

    # ランダム生成設定
    Config.RANDOM_S_RATIO_SUM_DEFAULT = args.sum
    Config.RANDOM_S_RATIO_SUM_CANDIDATES = []
    Config.RANDOM_T_REAGENTS = args.reagents
    Config.RANDOM_N_TARGETS = args.targets
    Config.RANDOM_K_RUNS = args.cases
    Config.MAX_LEVEL_DIFF = None
    Config.HETERO_RATIOS = "1:1,2:1,1:2"
    Config.HETERO_MULTIPLE_ONLY = True

    import random
    random.seed(args.seed)
    gen = RandomScenarioGenerator(Config)
    scenarios = gen.generate_batch_configs(args.cases)
    use_peer = (args.peer == "on")

    # 出力ディレクトリ
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("bench_results", f"bench_{ts}")
    os.makedirs(out_dir, exist_ok=True)

    print(f"設定: 合計{args.sum}, 試薬{args.reagents}, 液滴{args.targets}, "
          f"{len(scenarios)}ケース, 各{args.time}秒, ピア={args.peer}")
    print(f"出力先: {out_dir}")
    print("=" * 70)

    # 各パラメータ設定の集計
    agg = {name: {"opt": 0, "feas": 0, "time": 0.0, "nw": 0} for name in PARAM_SETS}
    mismatch_cases = []  # 解が一致しなかったケース番号

    for ci, rc in enumerate(scenarios):
        targets = rc["targets"]
        print(f"\n[ケース{ci+1}] {[t['ratios'] for t in targets]}")
        print(f"  {'設定':<12} {'nw':>4} {'状態':>9} {'時間':>9}")
        nw_values = {}
        baseline_analysis = None
        for name, fn in PARAM_SETS.items():
            nw, st, el, analysis = solve_with(targets, fn, args.time, use_peer)
            print(f"  {name:<12} {str(nw):>4} {st:>9} {el:>7.1f}s")
            nw_values[name] = nw
            if name == "baseline":
                baseline_analysis = analysis
            if nw is not None:
                agg[name]["nw"] += nw
                agg[name]["time"] += el
                if st == "OPTIMAL":
                    agg[name]["opt"] += 1
                elif st == "FEASIBLE":
                    agg[name]["feas"] += 1
        # 解の一致チェック(最適性を保てているかの検証)
        vals = [v for v in nw_values.values() if v is not None]
        if vals and len(set(vals)) > 1:
            print(f"  ※注意: 設定間でnwが不一致 {nw_values}")
            mismatch_cases.append(ci + 1)

        # このケースの解(baseline)を木画像と詳細テキストで保存(検証用)
        if baseline_analysis is not None:
            tree_png = os.path.join(out_dir, f"case{ci+1}_tree.png")
            ok = draw_solution_tree(
                baseline_analysis, tree_png,
                title=f"Case{ci+1} nw={baseline_analysis.get('total_waste')} "
                      f"({'peer' if use_peer else 'no-peer'})")
            detail_txt = os.path.join(out_dir, f"case{ci+1}_detail.txt")
            save_solution_detail(detail_txt, baseline_analysis, label=f"ケース{ci+1}")
            if ok:
                print(f"  解の木画像: {tree_png}")
            print(f"  解の詳細  : {detail_txt}")

    # 全体サマリ(画面)
    print("\n" + "=" * 70)
    print("  サマリ(全ケース合計)")
    print(f"  {'設定':<12} {'OPTIMAL数':>9} {'時間切れ':>8} {'合計nw':>7} {'合計時間':>10}")
    summary_rows = []
    for name in PARAM_SETS:
        a = agg[name]
        print(f"  {name:<12} {a['opt']:>9} {a['feas']:>8} {a['nw']:>7} {a['time']:>8.1f}s")
        summary_rows.append([name, a["opt"], a["feas"], a["nw"], f"{a['time']:.1f}"])
    print("=" * 70)
    print("  読み方: OPTIMAL数が多く合計時間が短い設定ほど、証明が速い。")
    print("         合計nwは全設定で同じはず(違えば時間切れの未到達が混在)。")

    # 要約ファイル保存
    notes = [
        f"問題設定: 合計{args.sum}, 試薬{args.reagents}, 液滴{args.targets}, "
        f"{len(scenarios)}ケース, 各{args.time}秒, ピア={args.peer}",
        "OPTIMAL数が多く合計時間が短い設定ほど証明が速い。",
        "合計nwは全設定で一致するはず(最適性を保った比較の検証)。",
    ]
    if mismatch_cases:
        notes.append(f"※ 解が不一致だったケース: {mismatch_cases} "
                     f"(時間切れで最適未到達の設定が混在 → --time を増やす)")
    else:
        notes.append("※ 全ケースで全設定のnwが一致 = 最適性を保った比較ができている。")
    summary_path = os.path.join(out_dir, "summary.txt")
    save_summary(summary_path,
                 ["設定", "OPTIMAL数", "時間切れ", "合計nw", "合計時間"],
                 summary_rows, notes)
    print(f"\n要約ファイル: {summary_path}")
    print(f"解の木画像・詳細: {out_dir}/case*_tree.png, case*_detail.txt")


if __name__ == "__main__":
    main()