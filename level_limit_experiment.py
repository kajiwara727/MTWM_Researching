#!/usr/bin/env python3
"""
階層制限(MAX_LEVEL_DIFF)の有無で、3手法の解にどれだけ差が出るかを比較する。

階層制限 = エッジ(共有)が何階層離れたノードまで繋げるかの条件。
  - 制限なし(None): 何階層離れていても共有可能
  - 制限1: 1階層差までしか共有できない(従来の比較設定)

比較する6通り:
  MTWM(ピアなし) / 卒論(等重きピア) / 提案(異重きピア)
    × 階層制限なし / 階層制限1

各設定で総廃棄を測り、「制限あり vs なし」で解がどれだけ変わるかを見る。

使い方:
  python3 level_limit_experiment.py --cases 100 --time 60 --targets 2 --sums 72
出力(level_results/):
  summary.txt, cases_raw.csv, waste_by_setting.png
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
from bench_output import save_summary, draw_bar_chart, save_csv, draw_solution_tree, save_solution_detail


def solve(targets, method, level_diff, time_limit, want_solution=False):
    """method: 'mtwm'(ピアなし)/'thesis'(等重き)/'proposed'(異重き)
    level_diff: None(制限なし) または 整数(階層制限)
    want_solution=True なら analysis 全体も返す(画像保存用)。
    戻り値: (waste, operations, reagents, status, elapsed[, analysis])
    """
    if method == "mtwm":
        Config.PEER_NODE_LIMIT = 0
        Config.ENABLE_HETERO_PEER = False
    elif method == "thesis":
        Config.PEER_NODE_LIMIT = "half_p_group"
        Config.ENABLE_HETERO_PEER = False
    else:  # proposed
        Config.PEER_NODE_LIMIT = "half_p_group"
        Config.ENABLE_HETERO_PEER = True
    Config.HETERO_RATIOS = "1:1,2:1,1:2"
    Config.HETERO_MULTIPLE_ONLY = True
    Config.MAX_LEVEL_DIFF = level_diff
    try:
        forest = build_dfmm_forest(targets)
        pmaps = calculate_p_values_from_structure(forest, targets)
        t_start = time.time()  # ★実行時間の測定開始
        with contextlib.redirect_stdout(io.StringIO()):
            prob = MTWMProblem(targets, forest, pmaps)
            solver = OrToolsSolver(prob, objective_mode="waste")
            solver.solver.parameters.log_search_progress = False
            solver.solver.parameters.max_time_in_seconds = time_limit
            _m, _v, a, _t = solver.solve()
        elapsed = time.time() - t_start  # ★所要時間(秒)
        if a is None:
            return (None,) * (6 if want_solution else 5)
        nw = a["total_waste"]
        ops = a.get("total_operations")
        nr = a.get("total_reagent_units")
        st = a.get("solver_status", "?")
        if want_solution:
            return nw, ops, nr, st, elapsed, a
        return nw, ops, nr, st, elapsed
    except Exception:
        return (None,) * (6 if want_solution else 5)


def main():
    ap = argparse.ArgumentParser(description="階層制限あり/なしの3手法比較")
    ap.add_argument("--cases", type=int, default=100)
    ap.add_argument("--time", type=float, default=60.0)
    ap.add_argument("--reagents", type=int, default=3)
    ap.add_argument("--targets", type=int, default=2)
    ap.add_argument("--sums", type=str, default="72")
    ap.add_argument("--limit", type=int, default=1,
                    help="比較する階層制限の値(デフォルト1=上下1階層)")
    ap.add_argument("--save-images", action="store_true",
                    help="全ケース×全手法の解の木画像を保存する(ケース数が少ないとき推奨)")
    ap.add_argument("--cap-mode", type=str, default=None, choices=["min", "max"],
                    help="出力重み上限の方式。min=小さい方以下(従来), "
                         "max=大きい方以下+既存重み限定。未指定ならconfigの値。")
    ap.add_argument("--seed", type=int, default=None,
                    help="乱数シード。同じseedなら同じケース集合が生成される。"
                         "方式比較(min/max等)を公平にするため指定する。")
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
    print(f"生成: {len(scenarios)}ケース (総和={Config.RANDOM_S_RATIO_SUM_CANDIDATES})\n")

    # 6設定: (method, level_diff, ラベル)
    settings = [
        ("mtwm", None, "MTWM_nolimit"),
        ("thesis", None, "thesis_nolimit"),
        ("proposed", None, "proposed_nolimit"),
        ("mtwm", args.limit, f"MTWM_limit{args.limit}"),
        ("thesis", args.limit, f"thesis_limit{args.limit}"),
        ("proposed", args.limit, f"proposed_limit{args.limit}"),
    ]

    # 出力先を先に作る(画像保存のため)。フォルダ名に実験条件を含める。
    ts = time.strftime("%Y%m%d_%H%M%S")
    sums_tag = args.sums.replace(",", "-")
    cap_tag = getattr(Config, "HETERO_PNEW_CAP_MODE", "min")
    seed_tag = f"_seed{args.seed}" if args.seed is not None else ""
    # 例: level_2T_sums54-72_t3_limit1_capmin_seed42_20260615_153000
    exp_tag = f"level_{args.targets}T_sums{sums_tag}_t{args.reagents}_limit{args.limit}_cap{cap_tag}{seed_tag}_{ts}"
    out_dir = os.path.join("level_results", exp_tag)
    os.makedirs(out_dir, exist_ok=True)
    print(f"出力先: {out_dir}")

    # 集計
    totals_nw = {s[2]: 0 for s in settings}
    totals_ops = {s[2]: 0 for s in settings}
    totals_nr = {s[2]: 0 for s in settings}
    totals_time = {s[2]: 0.0 for s in settings}
    non_opt = {s[2]: 0 for s in settings}
    tested = 0
    case_rows = []  # 全ケース×全手法の基礎情報

    for rc in scenarios:
        targets = rc["targets"]
        run_name = rc.get("run_name", f"case{tested+1}")
        res = {}      # label -> (nw, ops, nr, st, elapsed)
        analyses = {} # label -> analysis(画像用)
        skip = False
        for method, ld, label in settings:
            if args.save_images:
                nw, ops, nr, st, elapsed, a = solve(targets, method, ld, args.time, want_solution=True)
                analyses[label] = a
            else:
                nw, ops, nr, st, elapsed = solve(targets, method, ld, args.time)
            if nw is None:
                skip = True
                break
            res[label] = (nw, ops, nr, st, elapsed)
        if skip:
            continue
        tested += 1

        # 基礎情報を集計
        for _, _, label in settings:
            nw, ops, nr, st, elapsed = res[label]
            totals_nw[label] += nw
            totals_ops[label] += ops if ops is not None else 0
            totals_nr[label] += nr if nr is not None else 0
            totals_time[label] += elapsed if elapsed is not None else 0
            if st != "OPTIMAL":
                non_opt[label] += 1

        # ★全ケースの生データ行(全手法の nw, ops, nr, time, status)
        row = [run_name, ";".join(str(t["ratios"]) for t in targets),
               ";".join(str(t["factors"]) for t in targets)]
        for _, _, label in settings:
            nw, ops, nr, st, elapsed = res[label]
            row += [nw, ops, nr, f"{elapsed:.2f}", st]
        case_rows.append(row)

        # ★画像保存(全ケース×全手法)
        if args.save_images:
            case_dir = os.path.join(out_dir, "cases", run_name)
            os.makedirs(case_dir, exist_ok=True)
            for _, _, label in settings:
                a = analyses.get(label)
                if a is not None:
                    nw = res[label][0]
                    draw_solution_tree(
                        a, os.path.join(case_dir, f"{label}.png"),
                        title=f"{run_name} {label} nw={nw}")
                    save_solution_detail(
                        os.path.join(case_dir, f"{label}.txt"), a,
                        label=f"{run_name} {label}")

    if tested == 0:
        print("有効ケースなし")
        return

    # 表示
    print("=" * 90)
    print(f"  階層制限あり/なしの比較  [{tested}ケース]")
    print("=" * 90)
    print(f"  {'設定':<22} {'廃棄nw':>8} {'混合操作':>8} {'試薬nr':>8} "
          f"{'平均時間s':>9} {'時間切れ':>8}")
    for _, _, label in settings:
        avg_t = totals_time[label] / tested
        print(f"  {label:<22} {totals_nw[label]:>8} {totals_ops[label]:>8} "
              f"{totals_nr[label]:>8} {avg_t:>9.2f} {100*non_opt[label]/tested:>6.0f}%")
    print("=" * 90)
    # 制限の影響(各手法で制限なし→制限ありの廃棄増加)
    print("\n  ★階層制限の影響(廃棄nwの増加):")
    for method in ["mtwm", "thesis", "proposed"]:
        nolimit_label = next(l for m, d, l in settings if m == method and d is None)
        limit_label = next(l for m, d, l in settings if m == method and d == args.limit)
        diff = totals_nw[limit_label] - totals_nw[nolimit_label]
        print(f"    {method}: 制限なし{totals_nw[nolimit_label]} → "
              f"制限{args.limit}で{totals_nw[limit_label]} (増加{diff})")
    print("=" * 90)

    # 出力(要約)
    rows = []
    for _, _, label in settings:
        avg_t = totals_time[label] / tested
        rows.append([label, totals_nw[label], totals_ops[label], totals_nr[label],
                     f"{avg_t:.2f}", f"{100*non_opt[label]/tested:.0f}%"])
    notes = [
        f"設定: targets={args.targets}, reagents={args.reagents}, "
        f"cases={args.cases}, time={args.time}s, sums={args.sums}, limit={args.limit}",
        f"テストケース数: {tested}",
        "階層制限 = エッジが何階層離れたノードまで共有できるか(None=制限なし)。",
        "廃棄nw/混合操作/試薬nr/実行時間 を全手法×制限有無で比較。",
        "平均時間 = 1ケースあたりのソルバー所要時間(秒)。時間切れ時はtime上限に近い。",
        "制限ありで廃棄が増える = 制限が解を悪くしている。",
        ("全ケース×全手法の解の木画像を cases/ に保存済み。"
         if args.save_images else "画像未保存(--save-images で保存)。"),
    ]
    save_summary(os.path.join(out_dir, f"summary_{exp_tag}.txt"),
                 ["設定", "廃棄nw", "混合操作", "試薬nr", "平均時間s", "時間切れ"],
                 rows, notes)

    # 生データCSV(全ケース×全手法の基礎情報 + 実行時間)
    csv_header = ["run_name", "ratios", "factors"]
    for _, _, label in settings:
        csv_header += [f"{label}_nw", f"{label}_ops", f"{label}_nr",
                       f"{label}_time", f"{label}_status"]
    save_csv(os.path.join(out_dir, f"cases_{exp_tag}.csv"), csv_header, case_rows)

    # グラフ: 6設定の廃棄
    labels = [s[2] for s in settings]
    draw_bar_chart(labels, [[totals_nw[l] for l in labels]],
                   os.path.join(out_dir, f"waste_{exp_tag}.png"),
                   title=f"Total waste ({args.targets}T sums{sums_tag} limit{args.limit})",
                   ylabel="Total waste nw")
    print(f"\n要約: {out_dir}/summary_{exp_tag}.txt")
    print(f"生データCSV: {out_dir}/cases_{exp_tag}.csv")
    print(f"グラフ: {out_dir}/waste_{exp_tag}.png")
    if args.save_images:
        print(f"全ケース×全手法の画像: {out_dir}/cases/")


if __name__ == "__main__":
    main()