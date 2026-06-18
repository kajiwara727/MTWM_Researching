#!/usr/bin/env python3
"""
異重き混合が「いつ効くか」を理論的に特徴づけ、統計的に検証するスクリプト。

これまでの予備分析で見えた仮説:
  [仮説1] 効くには深さの多様性が要る(異なる深さのツリーが混在)。
  [仮説2] 倍数関係の重みペアが「同一ツリー内」にあると効く。
          「ツリー間」のペアは二重役割の矛盾で効きにくい。

各ランダムケースについて、
  - 提案(異重き)が卒論(等重き)より廃棄を減らしたか
  - 構造的特徴(深さの多様性、同一ツリー内/ツリー間の倍数ペア数)
を記録し、効く条件との相関を集計・可視化する。

使い方:
  python3 condition_analysis.py --cases 300 --time 20
出力(cond_results/cond_日時/):
  summary.txt          効く/効かないケースの特徴の比較表
  condition_chart.png  同一ツリー内ペア有無での改善率の棒グラフ
"""
import io
import os
import time
import argparse
import contextlib
import statistics
from collections import defaultdict

from utils.config_loader import Config
from core.generator import RandomScenarioGenerator
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.model.problem import MTWMProblem
from core.solver.engine import OrToolsSolver
from bench_output import save_summary, draw_bar_chart, save_csv, draw_solution_tree, save_solution_detail


def save_case_solution(targets, out_dir, tag, time_limit):
    """効いたケースを解き直して、解の木と詳細を保存する(検証用)。"""
    Config.PEER_NODE_LIMIT = "half_p_group"
    Config.ENABLE_HETERO_PEER = True
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
            return
        import os as _os
        case_dir = _os.path.join(out_dir, "cases", tag)
        _os.makedirs(case_dir, exist_ok=True)
        draw_solution_tree(a, _os.path.join(case_dir, "tree.png"),
                           title=f"{tag} nw={a.get('total_waste')}")
        save_solution_detail(_os.path.join(case_dir, "detail.txt"), a,
                             label=f"{tag} ratios={[t['ratios'] for t in targets]}")
    except Exception:
        pass


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


def extract_features(targets):
    """ターゲット群の構造的特徴を抽出する。"""
    forest = build_dfmm_forest(targets)
    pmaps = calculate_p_values_from_structure(forest, targets)
    weight_loc = defaultdict(list)  # weight -> [(tree, level)]
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
    for i, a in enumerate(ws):
        for b in ws[i + 1:]:
            if max(a, b) % min(a, b) != 0:
                continue
            for (ta, _la) in weight_loc[a]:
                for (tb, _lb) in weight_loc[b]:
                    if ta == tb:
                        same_tree_mult += 1
                    else:
                        cross_tree_mult += 1
    return {
        "multi_depth": len(set(len(t["factors"]) for t in targets)) > 1,
        "n_weight_types": len(ws),
        "same_tree_mult": same_tree_mult,
        "cross_tree_mult": cross_tree_mult,
    }


def main():
    ap = argparse.ArgumentParser(description="異重き混合が効く条件の特徴づけ・検証")
    ap.add_argument("--cases", type=int, default=200)
    ap.add_argument("--time", type=float, default=20.0)
    ap.add_argument("--reagents", type=int, default=3)
    ap.add_argument("--targets", type=int, default=3)
    ap.add_argument("--sums", type=str, default="18,36,54,72",
                    help="総和候補。★段数の違う総和を混ぜること(3段:18,24,27,36,48 / "
                         "4段:54,72,108)。同じ段数だけだと深さがばらつかず効くケースが出ない。")
    ap.add_argument("--save-cases", type=int, default=0,
                    help="効いたケースの解の木・詳細を保存する数(0=保存しない)。検証用。")
    ap.add_argument("--cap-mode", type=str, default=None, choices=["min", "max"],
                    help="出力重み上限の方式。min=小さい方以下(従来), "
                         "max=大きい方以下+既存重み限定。未指定ならconfigの値。")
    ap.add_argument("--seed", type=int, default=None,
                    help="乱数シード。同じseedなら同じケース集合が生成される。"
                         "方式比較(1:1 vs 任意比, min/max等)を公平にするため指定する。")
    args = ap.parse_args()

    # ★乱数シード固定(指定があれば)。同じseedで同じケース集合になり公平に比較できる。
    if args.seed is not None:
        import random
        random.seed(args.seed)

    # ★出力重み上限の方式(指定があればconfigを上書き)
    if args.cap_mode is not None:
        Config.HETERO_PNEW_CAP_MODE = args.cap_mode

    Config.RANDOM_T_REAGENTS = args.reagents
    Config.RANDOM_N_TARGETS = args.targets
    Config.RANDOM_S_RATIO_SUM_CANDIDATES = [int(s) for s in args.sums.split(",")]
    Config.RANDOM_S_RATIO_SUM_SEQUENCE = []
    Config.RANDOM_K_RUNS = args.cases

    gen = RandomScenarioGenerator(Config)
    scenarios = gen.generate_batch_configs(args.cases)
    print(f"生成: {len(scenarios)}ケース (総和候補={Config.RANDOM_S_RATIO_SUM_CANDIDATES})")

    # ★深さの多様性チェック: 生成ケースに異なる段数のツリーが混在するか
    n_multi = sum(1 for rc in scenarios
                  if len(set(len(t["factors"]) for t in rc["targets"])) > 1)
    print(f"  深さが多様なケース: {n_multi}/{len(scenarios)} "
          f"({100*n_multi/len(scenarios) if scenarios else 0:.0f}%)")
    if n_multi == 0:
        print("  ★警告: 深さが多様なケースが0。総和候補が全て同じ段数の可能性。")
        print("    段数: 3段=18,24,27,36,48 / 4段=54,72,108。段数の違う総和を --sums で混ぜること。")

    improved = []
    not_improved = []
    non_optimal = 0
    tested = 0
    case_rows = []  # ★全ケースの生データ
    improved_targets = []  # 効いたOPTIMALケースのtargets(解保存用)

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
        feat = extract_features(targets)
        feat["reduction"] = wt - wp
        # ★生データを記録
        case_rows.append([
            rc.get("run_name", ""),
            ";".join(str(t["ratios"]) for t in targets),
            ";".join(str(t["factors"]) for t in targets),
            wt, wp, wt - wp,
            int(feat["multi_depth"]),
            feat["n_weight_types"],
            feat["same_tree_mult"],
            feat["cross_tree_mult"],
            int(wp < wt),
            st, sp,
        ])
        if wp < wt:
            improved.append(feat)
            # 効いてOPTIMALなケースだけ解保存対象に(時間切れの偽結果を除く)
            if is_opt and len(improved_targets) < args.save_cases:
                improved_targets.append((rc.get("run_name", f"case{tested}"), targets))
        else:
            not_improved.append(feat)

    if tested == 0:
        print("有効ケースなし")
        return

    def stat(feats, key):
        return statistics.mean(f[key] for f in feats) if feats else 0

    def rate(feats, cond):
        return 100 * sum(1 for f in feats if cond(f)) / len(feats) if feats else 0

    # 集計表示
    print(f"\n{'='*60}")
    print(f"  異重き混合が効く条件の分析  [{tested}ケース, 時間切れ{100*non_optimal/tested:.0f}%]")
    print(f"{'='*60}")
    print(f"  効いた: {len(improved)}件 / 効かない: {len(not_improved)}件\n")
    for feats, name in [(improved, "効いたケース"), (not_improved, "効かないケース")]:
        if not feats:
            continue
        print(f"  {name} ({len(feats)}件):")
        print(f"    深さが多様な率        : {rate(feats, lambda f: f['multi_depth']):.0f}%")
        print(f"    同一ツリー内倍数ペア(平均): {stat(feats,'same_tree_mult'):.2f}")
        print(f"    ツリー間倍数ペア(平均)    : {stat(feats,'cross_tree_mult'):.2f}")
        print(f"    同一ツリー内ペアを持つ率  : {rate(feats, lambda f: f['same_tree_mult']>0):.0f}%")
        print()

    # 「同一ツリー内ペアの有無」で改善率を比較(仮説2の検証)
    all_feats = [(f, True) for f in improved] + [(f, False) for f in not_improved]
    with_same = [imp for f, imp in all_feats if f["same_tree_mult"] > 0]
    without_same = [imp for f, imp in all_feats if f["same_tree_mult"] == 0]
    rate_with = 100 * sum(with_same) / len(with_same) if with_same else 0
    rate_without = 100 * sum(without_same) / len(without_same) if without_same else 0
    print(f"  ★仮説2の検証: 同一ツリー内の倍数ペアの有無で改善率を比較")
    print(f"    同一ツリー内ペアあり: 改善率 {rate_with:.1f}% ({len(with_same)}件)")
    print(f"    同一ツリー内ペアなし: 改善率 {rate_without:.1f}% ({len(without_same)}件)")
    print(f"{'='*60}\n")

    # 出力。フォルダ名・ファイル名に実験条件を含める。
    ts = time.strftime("%Y%m%d_%H%M%S")
    sums_tag = args.sums.replace(",", "-")
    ratios_tag = Config.HETERO_RATIOS.replace(":", "").replace(",", "-")
    cap_tag = getattr(Config, "HETERO_PNEW_CAP_MODE", "min")
    seed_tag = f"_seed{args.seed}" if args.seed is not None else ""
    # 例: cond_2T_sums72_t3_ratios11-21-12_capmin_seed42_20260615_153000
    exp_tag = (f"cond_{args.targets}T_sums{sums_tag}_t{args.reagents}"
               f"_ratios{ratios_tag}_cap{cap_tag}{seed_tag}_{ts}")
    out_dir = os.path.join("cond_results", exp_tag)
    os.makedirs(out_dir, exist_ok=True)
    print(f"出力先: {out_dir}")
    rows = [
        ["効いたケース", len(improved),
         f"{rate(improved, lambda f: f['multi_depth']):.0f}%",
         f"{stat(improved,'same_tree_mult'):.2f}",
         f"{stat(improved,'cross_tree_mult'):.2f}"],
        ["効かないケース", len(not_improved),
         f"{rate(not_improved, lambda f: f['multi_depth']):.0f}%",
         f"{stat(not_improved,'same_tree_mult'):.2f}",
         f"{stat(not_improved,'cross_tree_mult'):.2f}"],
    ]
    notes = [
        f"設定: targets={args.targets}, reagents={args.reagents}, "
        f"cases={args.cases}, time={args.time}s, sums={args.sums}, "
        f"HETERO_RATIOS={Config.HETERO_RATIOS}, "
        f"PNEW_CAP_MODE={getattr(Config,'HETERO_PNEW_CAP_MODE','min')}",
        f"テストケース数: {tested}, 時間切れ: {100*non_optimal/tested:.0f}%",
        f"仮説2の検証: 同一ツリー内ペアあり改善率 {rate_with:.1f}% vs なし {rate_without:.1f}%",
        "仮説1: 効くには深さの多様性が要る(効いたケースの深さ多様率が高いはず)。",
        "仮説2: 倍数ペアが同一ツリー内にあると効く(ツリー間は二重役割の矛盾で効きにくい)。",
    ]
    save_summary(os.path.join(out_dir, f"summary_{exp_tag}.txt"),
                 ["分類", "件数", "深さ多様率", "同一ツリー内ペア", "ツリー間ペア"],
                 rows, notes)
    # ★全ケースの生データCSV
    save_csv(os.path.join(out_dir, f"cases_{exp_tag}.csv"),
             ["run_name", "ratios", "factors", "nw_thesis", "nw_proposed", "reduction",
              "multi_depth", "n_weight_types", "same_tree_mult", "cross_tree_mult",
              "improved", "status_thesis", "status_proposed"],
             case_rows)
    draw_bar_chart(
        ["same-tree pair: yes", "same-tree pair: no"],
        [[rate_with, rate_without]],
        os.path.join(out_dir, f"chart_{exp_tag}.png"),
        title="Improvement rate by presence of same-tree multiple-pair",
        ylabel="Improvement rate (%)")
    # ★効いたケースの解の木・詳細を保存(検証用、--save-cases 指定時)
    if improved_targets:
        print(f"\n効いたケースの解を保存中({len(improved_targets)}件)...")
        for tag, tgts in improved_targets:
            save_case_solution(tgts, out_dir, tag, args.time)
        print(f"  → {out_dir}/cases/ に解の木と詳細を保存")

    print(f"要約: {out_dir}/summary_{exp_tag}.txt")
    print(f"生データCSV: {out_dir}/cases_{exp_tag}.csv")
    print(f"グラフ: {out_dir}/chart_{exp_tag}.png")


if __name__ == "__main__":
    main()