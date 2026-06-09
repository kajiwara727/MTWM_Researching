#!/usr/bin/env python3
"""
3段階比較スキャン: 元MTWM(ピアなし) / 卒論(等重きピア) / 提案(等重き+異重き)。

ランダムケースは config.py の RANDOM_* 設定で制御される(既存の
RandomScenarioGenerator を利用):
  RANDOM_N_TARGETS         作る液滴数 (ターゲット数 μ、マルチサンプル調製)
  RANDOM_T_REAGENTS        試薬の種類数 t
  RANDOM_S_RATIO_SUM_*     成分比率の合計 (18, 135 など)
  RANDOM_K_RUNS            生成するケース数

使い方:
  python3 scan.py                 # config の RANDOM_* に従ってスキャン
  python3 scan.py --time 20       # 1ケースのソルバー時間(秒)
  python3 scan.py --cases 100     # ケース数(RANDOM_K_RUNS を上書き)
  python3 scan.py --level-diff 1  # 共有を上下 N レベルに制限(MAX_LEVEL_DIFF)

config.py の HETERO_* 設定(異重きの比・絞り込み)も反映される。
出力: 3段階の総廃棄 nw / 試薬 nr と、各段の改善ケース率。
"""
import io
import argparse
import contextlib

from utils.config_loader import Config
from core.generator import RandomScenarioGenerator
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.model.problem import MTWMProblem
from core.solver.engine import OrToolsSolver
from hetero_usage import (collect_hetero_usage, summarize_batch,
                          format_batch_summary, append_usage_log)


def solve_waste(targets, mode, time_limit, want_usage=False):
    """指定ターゲットを解いて(総廃棄, 総試薬, 異重き候補数)を返す。
    want_usage=True のとき (waste, nr, n_hetero, usage) を返す。
    mode: 'orig'=ピアなし(元MTWM), 'thesis'=等重きピアのみ(卒論),
          'proposed'=等重き+異重き(提案)
    """
    if mode == "orig":
        Config.PEER_NODE_LIMIT = 0
        Config.ENABLE_HETERO_PEER = False
    elif mode == "thesis":
        Config.PEER_NODE_LIMIT = "half_p_group"
        Config.ENABLE_HETERO_PEER = False
    else:  # proposed
        Config.PEER_NODE_LIMIT = "half_p_group"
        Config.ENABLE_HETERO_PEER = True
    try:
        forest = build_dfmm_forest(targets)
        pmaps = calculate_p_values_from_structure(forest, targets)
        with contextlib.redirect_stdout(io.StringIO()):
            prob = MTWMProblem(targets, forest, pmaps)
            n_hetero = sum(1 for p in prob.peer_nodes if p.get("is_hetero"))
            solver = OrToolsSolver(prob, objective_mode="waste")
            solver.solver.parameters.log_search_progress = False
            solver.solver.parameters.max_time_in_seconds = time_limit
            _m, _v, a, _t = solver.solve()
        if a is None:
            return (None, None, n_hetero, None) if want_usage else (None, None, n_hetero)
        if want_usage:
            usage = collect_hetero_usage(solver)
            return a["total_waste"], a["total_reagent_units"], n_hetero, usage
        return a["total_waste"], a["total_reagent_units"], n_hetero
    except Exception:
        return (None, None, 0, None) if want_usage else (None, None, 0)


def run_scan(time_limit, usage_log=None):
    # config の RANDOM_* に従ってランダムケースを生成(既存ジェネレータ)
    generator = RandomScenarioGenerator(Config)
    scenarios = generator.generate_batch_configs(Config.RANDOM_K_RUNS)
    print(f"生成されたケース数: {len(scenarios)} "
          f"(N_TARGETS={Config.RANDOM_N_TARGETS}, T_REAGENTS={Config.RANDOM_T_REAGENTS})")

    tested = 0
    tot = {"orig": 0, "thesis": 0, "proposed": 0}
    tot_nr = {"orig": 0, "thesis": 0, "proposed": 0}
    prop_beats_thesis = 0
    thesis_beats_orig = 0
    prop_beats_orig = 0
    tot_cand = 0
    deep_total = 0
    deep_prop_beats = 0
    usages = []  # 各ケースの異重きピア使用状況

    for run_config in scenarios:
        targets = run_config["targets"]
        has_deep = any(len(t.get("factors", [])) >= 4 for t in targets)
        w_orig, r_orig, _ = solve_waste(targets, "orig", time_limit)
        w_thesis, r_thesis, _ = solve_waste(targets, "thesis", time_limit)
        w_prop, r_prop, n_cand, usage = solve_waste(
            targets, "proposed", time_limit, want_usage=True)
        if None in (w_orig, w_thesis, w_prop):
            continue
        if w_orig == 0:
            continue

        tested += 1
        tot["orig"] += w_orig
        tot["thesis"] += w_thesis
        tot["proposed"] += w_prop
        tot_nr["orig"] += r_orig
        tot_nr["thesis"] += r_thesis
        tot_nr["proposed"] += r_prop
        tot_cand += n_cand
        if usage:
            usages.append(usage)
            if usage_log and usage["used"] > 0:
                label = run_config.get("run_name", "") + " " + \
                    str([(t["ratios"], t["factors"]) for t in targets])
                append_usage_log(usage, usage_log, label)
        if has_deep:
            deep_total += 1
        if w_prop < w_thesis:
            prop_beats_thesis += 1
            if has_deep:
                deep_prop_beats += 1
        if w_thesis < w_orig:
            thesis_beats_orig += 1
        if w_prop < w_orig:
            prop_beats_orig += 1

    if tested == 0:
        print("有効なテストケースがありませんでした(全ケース廃棄0か解けず)。")
        return

    def pct(x):
        return 100 * x / tested

    print(f"\n{'='*60}")
    print(f"  3段階比較: 元MTWM → 卒論(等重き) → 提案(異重き)   [{tested}ケース]")
    print(f"{'='*60}")
    print(f"  総廃棄 nw:")
    print(f"    (1) 元MTWM (ピアなし)      : {tot['orig']}")
    print(f"    (2) 卒論   (等重きピア)    : {tot['thesis']}  "
          f"(元比 -{tot['orig']-tot['thesis']}, "
          f"{100*(tot['orig']-tot['thesis'])/tot['orig']:.1f}%)")
    print(f"    (3) 提案   (等重き+異重き) : {tot['proposed']}  "
          f"(元比 -{tot['orig']-tot['proposed']}, "
          f"{100*(tot['orig']-tot['proposed'])/tot['orig']:.1f}%)")
    print(f"  総試薬 nr:")
    print(f"    元={tot_nr['orig']}  卒論={tot_nr['thesis']}  提案={tot_nr['proposed']}")
    print(f"  改善ケース数:")
    print(f"    卒論が元MTWMを改善      : {thesis_beats_orig} ({pct(thesis_beats_orig):.1f}%)")
    print(f"    提案が卒論を改善(新規性): {prop_beats_thesis} ({pct(prop_beats_thesis):.1f}%)")
    print(f"    提案が元MTWMを改善(累積): {prop_beats_orig} ({pct(prop_beats_orig):.1f}%)")
    print(f"  平均異重きピア候補数      : {tot_cand/tested:.1f}")
    if deep_total:
        print(f"  深いツリー(4段+) {deep_total}ケース中、提案が卒論を改善: "
              f"{deep_prop_beats} ({100*deep_prop_beats/deep_total:.1f}%)")
    print(f"{'='*60}\n")

    # 異重きピア・混合比の使用状況サマリ
    if usages:
        batch = summarize_batch(usages)
        print(format_batch_summary(batch))
        if usage_log:
            with open(usage_log, "a", encoding="utf-8") as f:
                f.write("\n" + format_batch_summary(batch) + "\n")
            print(f"\n使用状況ログを {usage_log} に保存しました。")


def main():
    ap = argparse.ArgumentParser(description="3段階比較スキャン: 元MTWM/卒論/提案")
    ap.add_argument("--time", type=float, default=8.0, help="1ケースのソルバー時間(秒)")
    ap.add_argument("--cases", type=int, default=None,
                    help="ケース数(指定で RANDOM_K_RUNS を上書き)")
    ap.add_argument("--level-diff", type=int, default=None,
                    help="共有を上下 N レベルに制限(MAX_LEVEL_DIFF を上書き)")
    ap.add_argument("--log", type=str, default="hetero_usage_log.txt",
                    help="異重きピア使用状況の記録先(デフォルト hetero_usage_log.txt)")
    args = ap.parse_args()

    if args.cases is not None:
        Config.RANDOM_K_RUNS = args.cases
    if args.level_diff is not None:
        Config.MAX_LEVEL_DIFF = args.level_diff
        print(f"共有制限: MAX_LEVEL_DIFF={args.level_diff}")

    print(f"設定: HETERO_RATIOS={Config.HETERO_RATIOS}, "
          f"HETERO_MULTIPLE_ONLY={Config.HETERO_MULTIPLE_ONLY}, "
          f"S_RATIO_SUM={Config.RANDOM_S_RATIO_SUM_DEFAULT}")
    print("3段階: (1)元MTWM=ピアなし (2)卒論=等重きピア (3)提案=等重き+異重き")
    run_scan(args.time, usage_log=args.log)


if __name__ == "__main__":
    main()