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
import os
import time
import argparse
import contextlib

from utils.config_loader import Config
from core.generator import RandomScenarioGenerator
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.model.problem import MTWMProblem
from core.solver.engine import OrToolsSolver
from hetero_usage import (collect_hetero_usage, summarize_batch,
                          format_batch_summary, append_usage_log)
from bench_output import save_summary, draw_bar_chart, draw_solution_tree, save_solution_detail, save_csv


def solve_waste(targets, mode, time_limit, want_usage=False, level_diff="keep"):
    """指定ターゲットを解いて(総廃棄, 総試薬, 異重き候補数)を返す。
    want_usage=True のとき (waste, nr, n_hetero, usage) を返す。
    mode: 'orig'=ピアなし(元MTWM), 'thesis'=等重きピアのみ(卒論),
          'proposed'=等重き+異重き(提案)
    level_diff: "keep"=現在のConfig値のまま, None=制限なし, 整数=上下Nレベル制限。
    """
    if level_diff != "keep":
        Config.MAX_LEVEL_DIFF = level_diff
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
    showcase_targets = None  # 提案が卒論を改善し異重きを使った代表ケース
    case_rows = []  # ★全ケースの生データ(CSV用)

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

        # ★生データを1行記録(ターゲット比・factors・3手法の廃棄/試薬)
        case_rows.append([
            run_config.get("run_name", ""),
            ";".join(str(t["ratios"]) for t in targets),
            ";".join(str(t["factors"]) for t in targets),
            w_orig, w_thesis, w_prop,
            r_orig, r_thesis, r_prop,
            n_cand,
            usage["used"] if usage else 0,
            int(w_prop < w_thesis),  # 提案が卒論を改善したか
        ])

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
            # 代表ケース: 提案が卒論を改善し、異重きを実際に使ったケースを覚える
            if showcase_targets is None and w_prop < w_thesis and usage["used"] > 0:
                showcase_targets = targets
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

    # ===== 要約ファイル・グラフ・代表ケースの木画像を出力 =====
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("scan_results", f"scan_{ts}")
    os.makedirs(out_dir, exist_ok=True)

    # 要約ファイル
    rows = [
        ["元MTWM(ピアなし)", tot["orig"], tot_nr["orig"], "-"],
        ["卒論(等重きピア)", tot["thesis"], tot_nr["thesis"],
         f"{pct(thesis_beats_orig):.1f}%"],
        ["提案(等重き+異重き)", tot["proposed"], tot_nr["proposed"],
         f"{pct(prop_beats_orig):.1f}%"],
    ]
    notes = [
        f"テストケース数: {tested}",
        f"提案が卒論を改善(新規性): {prop_beats_thesis} ({pct(prop_beats_thesis):.1f}%)",
        f"平均異重きピア候補数: {tot_cand/tested:.1f}",
        f"設定: N_TARGETS={Config.RANDOM_N_TARGETS}, T_REAGENTS={Config.RANDOM_T_REAGENTS}, "
        f"HETERO_RATIOS={Config.HETERO_RATIOS}",
    ]
    if deep_total:
        notes.append(f"深いツリー(4段+) {deep_total}ケース中、提案が卒論を改善: "
                     f"{deep_prop_beats} ({100*deep_prop_beats/deep_total:.1f}%)")
    summary_path = os.path.join(out_dir, "summary.txt")
    save_summary(summary_path,
                 ["手法", "総廃棄nw", "総試薬nr", "元比改善率"], rows, notes)

    # ★全ケースの生データをCSVで保存(後から1件ずつ検証・再集計できる)
    csv_path = os.path.join(out_dir, "cases_raw.csv")
    save_csv(csv_path,
             ["run_name", "ratios", "factors",
              "nw_orig", "nw_thesis", "nw_proposed",
              "nr_orig", "nr_thesis", "nr_proposed",
              "hetero_candidates", "hetero_used", "proposed_beats_thesis"],
             case_rows)

    # グラフ: 3段階の総廃棄
    draw_bar_chart(
        ["orig MTWM", "thesis", "proposed"],
        [[tot["orig"], tot["thesis"], tot["proposed"]]],
        os.path.join(out_dir, "waste_3stage.png"),
        title="Total waste (nw): orig MTWM vs thesis vs proposed",
        ylabel="Total waste nw")

    # 代表ケースの解の木画像(提案で異重きを使い卒論を改善したケース)
    if showcase_targets is not None:
        _, _, _, _ = solve_waste(showcase_targets, "proposed", time_limit, want_usage=True)
        # 解の詳細を取り直して木画像化
        Config.PEER_NODE_LIMIT = "half_p_group"
        Config.ENABLE_HETERO_PEER = True
        forest = build_dfmm_forest(showcase_targets)
        pmaps = calculate_p_values_from_structure(forest, showcase_targets)
        with contextlib.redirect_stdout(io.StringIO()):
            prob = MTWMProblem(showcase_targets, forest, pmaps)
            solver = OrToolsSolver(prob, objective_mode="waste")
            solver.solver.parameters.log_search_progress = False
            solver.solver.parameters.max_time_in_seconds = time_limit
            _m, _v, a, _t = solver.solve()
        if a is not None:
            tree_png = os.path.join(out_dir, "showcase_tree.png")
            ok = draw_solution_tree(
                a, tree_png,
                title=f"Showcase: proposed nw={a.get('total_waste')} "
                      f"{[t['ratios'] for t in showcase_targets]}")
            detail_txt = os.path.join(out_dir, "showcase_detail.txt")
            save_solution_detail(detail_txt, a, label="代表ケース(提案・異重き使用)")
            if ok:
                print(f"代表ケースの木画像: {tree_png}")
            print(f"代表ケースの詳細  : {detail_txt}")

    print(f"\n要約ファイル: {summary_path}")
    print(f"生データCSV: {csv_path}")
    print(f"グラフ: {out_dir}/waste_3stage.png")


def solve_one(targets, mode, time_limit, level_diff="keep"):
    """1ケースを解いて (waste, status) を返す。status は OPTIMAL/FEASIBLE/None。"""
    if level_diff != "keep":
        Config.MAX_LEVEL_DIFF = level_diff
    if mode == "orig":
        Config.PEER_NODE_LIMIT = 0
        Config.ENABLE_HETERO_PEER = False
    elif mode == "thesis":
        Config.PEER_NODE_LIMIT = "half_p_group"
        Config.ENABLE_HETERO_PEER = False
    else:
        Config.PEER_NODE_LIMIT = "half_p_group"
        Config.ENABLE_HETERO_PEER = True
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


def run_restricted_scan(time_limit, level_diff=1):
    """[制限版比較] 共有を上下 level_diff レベルに制限した提案手法が、
    制限なし従来MTWM と同等以上になるかを検証する。
    比較:
      (A) 従来MTWM   : 制限なし + ピアなし(基準)
      (B) 制限+ピアなし: 上下制限 + ピアなし(制限の影響を見る対照)
      (C) 制限+提案   : 上下制限 + 等重き&異重きピア(提案)
    """
    generator = RandomScenarioGenerator(Config)
    scenarios = generator.generate_batch_configs(Config.RANDOM_K_RUNS)
    print(f"生成されたケース数: {len(scenarios)} "
          f"(共有制限: 上下{level_diff}レベル)")

    tested = 0
    tot = {"A": 0, "B": 0, "C": 0}
    c_ge_a = 0
    c_gt_a = 0
    c_lt_a = 0
    non_optimal = 0   # いずれかが時間切れ(非OPTIMAL)だったケース数

    for run_config in scenarios:
        targets = run_config["targets"]
        wA, sA = solve_one(targets, "orig", time_limit, level_diff=None)
        wB, sB = solve_one(targets, "orig", time_limit, level_diff=level_diff)
        wC, sC = solve_one(targets, "proposed", time_limit, level_diff=level_diff)
        if None in (wA, wB, wC):
            continue
        tested += 1
        tot["A"] += wA
        tot["B"] += wB
        tot["C"] += wC
        if "OPTIMAL" not in (sA, sB, sC) or sA != "OPTIMAL" or sB != "OPTIMAL" or sC != "OPTIMAL":
            non_optimal += 1
        if wC <= wA:
            c_ge_a += 1
        if wC < wA:
            c_gt_a += 1
        if wC > wA:
            c_lt_a += 1

    if tested == 0:
        print("有効なテストケースがありませんでした。")
        return

    def pct(x):
        return 100 * x / tested

    print(f"\n{'='*62}")
    print(f"  制限版比較: 従来MTWM(制限なし) vs 提案(上下{level_diff}制限+ピア)  [{tested}ケース]")
    print(f"{'='*62}")
    print(f"  ★時間切れ(非OPTIMAL)を含むケース: {non_optimal} ({pct(non_optimal):.1f}%)")
    if non_optimal > 0:
        print(f"    → 時間切れがあると結果が不正確。--time を増やすこと。")
    print(f"  総廃棄 nw:")
    print(f"    (A) 従来MTWM   (制限なし・ピアなし) : {tot['A']}")
    print(f"    (B) 制限のみ   (上下{level_diff}・ピアなし)   : {tot['B']}  "
          f"(Aとの差 {tot['B']-tot['A']:+d})")
    print(f"    (C) 提案       (上下{level_diff}・ピアあり)   : {tot['C']}  "
          f"(Aとの差 {tot['C']-tot['A']:+d})")
    print(f"  提案(C) vs 従来(A) のケース別:")
    print(f"    C が A 以上(同等以上に良い): {c_ge_a} ({pct(c_ge_a):.1f}%)")
    print(f"      うち C が A より良い      : {c_gt_a} ({pct(c_gt_a):.1f}%)")
    print(f"    C が A より悪い            : {c_lt_a} ({pct(c_lt_a):.1f}%)")
    print(f"{'='*62}")
    if tot["C"] <= tot["A"]:
        print("  → 提案は制限下でも従来MTWM(制限なし)と同等以上の総廃棄を達成。")
    else:
        print(f"  → 提案は従来に総廃棄で {tot['C']-tot['A']} 及ばず(制限の影響が残る)。")
    print()


def main():
    ap = argparse.ArgumentParser(description="3段階比較スキャン: 元MTWM/卒論/提案")
    ap.add_argument("--time", type=float, default=8.0, help="1ケースのソルバー時間(秒)")
    ap.add_argument("--cases", type=int, default=None,
                    help="ケース数(指定で RANDOM_K_RUNS を上書き)")
    ap.add_argument("--level-diff", type=int, default=None,
                    help="共有を上下 N レベルに制限(MAX_LEVEL_DIFF を上書き)")
    ap.add_argument("--log", type=str, default="hetero_usage_log.txt",
                    help="異重きピア使用状況の記録先(デフォルト hetero_usage_log.txt)")
    ap.add_argument("--restricted", type=int, default=None, metavar="N",
                    help="制限版比較モード: 従来MTWM(制限なし) vs 提案(上下Nレベル制限+ピア)")
    args = ap.parse_args()

    if args.cases is not None:
        Config.RANDOM_K_RUNS = args.cases
    if args.level_diff is not None:
        Config.MAX_LEVEL_DIFF = args.level_diff
        print(f"共有制限: MAX_LEVEL_DIFF={args.level_diff}")

    print(f"設定: HETERO_RATIOS={Config.HETERO_RATIOS}, "
          f"HETERO_MULTIPLE_ONLY={Config.HETERO_MULTIPLE_ONLY}, "
          f"S_RATIO_SUM={Config.RANDOM_S_RATIO_SUM_DEFAULT}")

    if args.restricted is not None:
        print(f"=== 制限版比較モード(従来MTWM制限なし vs 提案 上下{args.restricted}制限) ===")
        run_restricted_scan(args.time, level_diff=args.restricted)
    else:
        print("3段階: (1)元MTWM=ピアなし (2)卒論=等重きピア (3)提案=等重き+異重き")
        run_scan(args.time, usage_log=args.log)


if __name__ == "__main__":
    main()