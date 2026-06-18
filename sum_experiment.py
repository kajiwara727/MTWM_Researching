#!/usr/bin/env python3
"""
総和(ratio-sum)の設定を変えて、異重き混合の効き方を体系的に調べる実験。

2つの軸を比較する:
  軸1: 総和の与え方
    - "uniform"  : 全ターゲットを同じ総和に固定(卒論・論文準拠、深さが揃う)
    - "varied"   : ターゲットごとに候補から総和を選ぶ(深さがばらつく)
  軸2: 総和の値(複数パターン)

各設定で、3段階(元MTWM/卒論/提案)の総廃棄と、提案が卒論を改善した
ケース率、異重きピアの平均候補数を測る。
これにより「どの総和設定で異重きがどれだけ効くか」が体系的に分かる。

全て「総和固定 + 既約(gcd=1)」はジェネレータが標準で満たす。
"varied" は複数の総和候補からターゲットごとに選ぶ(各ターゲット内では固定総和)。

使い方(こちらの環境で実行):
  python3 sum_experiment.py --cases 100 --time 20
  python3 sum_experiment.py --cases 200 --time 30 --sums 18,24,36
  python3 sum_experiment.py --cases 100 --time 20 --varied-sets "18,36;24,36;18,24,36"
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
from bench_output import save_summary, draw_bar_chart, save_csv


def solve(targets, mode, time_limit):
    """mode: orig/thesis/proposed。(nw, status, n_hetero) を返す。"""
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
            nh = sum(1 for p in prob.peer_nodes if p.get("is_hetero"))
            solver = OrToolsSolver(prob, objective_mode="waste")
            solver.solver.parameters.log_search_progress = False
            solver.solver.parameters.max_time_in_seconds = time_limit
            _m, _v, a, _t = solver.solve()
        if a is None:
            return None, None, nh
        return a["total_waste"], a.get("solver_status", "?"), nh
    except Exception:
        return None, None, 0


def run_one_setting(label, time_limit, n_cases):
    """現在の Config 設定でケース生成し、3段階比較した結果を集計して返す。"""
    gen = RandomScenarioGenerator(Config)
    scenarios = gen.generate_batch_configs(n_cases)
    tested = 0
    tot = {"orig": 0, "thesis": 0, "proposed": 0}
    prop_beats_thesis = 0
    non_optimal = 0
    tot_cand = 0
    for rc in scenarios:
        targets = rc["targets"]
        wo, so, _ = solve(targets, "orig", time_limit)
        wt, st, _ = solve(targets, "thesis", time_limit)
        wp, sp, nh = solve(targets, "proposed", time_limit)
        if None in (wo, wt, wp):
            continue
        if wo == 0:
            continue
        tested += 1
        tot["orig"] += wo
        tot["thesis"] += wt
        tot["proposed"] += wp
        tot_cand += nh
        if "OPTIMAL" not in (so, st, sp) or so != "OPTIMAL" or st != "OPTIMAL" or sp != "OPTIMAL":
            non_optimal += 1
        if wp < wt:
            prop_beats_thesis += 1
    return {
        "label": label,
        "tested": tested,
        "tot": tot,
        "prop_beats_thesis": prop_beats_thesis,
        "non_optimal": non_optimal,
        "avg_cand": (tot_cand / tested) if tested else 0,
    }


def print_result(r):
    t = r["tested"]
    if t == 0:
        print(f"  [{r['label']}] 有効ケースなし")
        return
    tot = r["tot"]
    print(f"\n  ◆ {r['label']}  ({t}ケース, 時間切れ{100*r['non_optimal']/t:.0f}%)")
    print(f"     総廃棄 nw: 元MTWM={tot['orig']}, 卒論={tot['thesis']}, 提案={tot['proposed']}")
    if tot["orig"]:
        red_thesis = 100 * (tot["orig"] - tot["thesis"]) / tot["orig"]
        red_prop = 100 * (tot["orig"] - tot["proposed"]) / tot["orig"]
        print(f"     元比削減: 卒論 {red_thesis:.1f}%, 提案 {red_prop:.1f}%")
    print(f"     提案が卒論を改善したケース: {r['prop_beats_thesis']} "
          f"({100*r['prop_beats_thesis']/t:.1f}%)")
    print(f"     異重きピア平均候補数: {r['avg_cand']:.1f}")


def main():
    ap = argparse.ArgumentParser(description="総和設定(固定/ばらつき)の比較実験")
    ap.add_argument("--cases", type=int, default=100, help="各設定のケース数")
    ap.add_argument("--time", type=float, default=20.0, help="1ケースのソルバー時間(秒)")
    ap.add_argument("--sums", type=str, default="18,24,36",
                    help="uniform(固定)で試す総和のリスト 例 18,24,36")
    ap.add_argument("--varied-sets", type=str, default="18,36;18,24,36",
                    help="varied(ばらつき)で試す候補集合。; 区切りで複数、各集合は , 区切り")
    ap.add_argument("--reagents", type=int, default=3, help="試薬数 t")
    ap.add_argument("--targets", type=int, default=3, help="液滴数 μ")
    args = ap.parse_args()

    Config.RANDOM_T_REAGENTS = args.reagents
    Config.RANDOM_N_TARGETS = args.targets
    Config.MAX_LEVEL_DIFF = None
    Config.HETERO_RATIOS = "1:1,2:1,1:2"
    Config.HETERO_MULTIPLE_ONLY = True
    Config.RANDOM_K_RUNS = args.cases

    print("=" * 64)
    print(f"  総和設定の比較実験 (試薬{args.reagents}, 液滴{args.targets}, "
          f"各{args.cases}ケース, {args.time}秒)")
    print(f"  ※ 総和固定 + 既約(gcd=1) はジェネレータ標準")
    print("=" * 64)

    # 軸1-A: uniform(全ターゲット同じ総和に固定)を、各総和値で
    print("\n【軸A: 総和を全ターゲットで揃える(uniform, 深さが揃う)】")
    uniform_sums = [int(s) for s in args.sums.split(",")]
    results_uniform = []
    for s in uniform_sums:
        Config.RANDOM_S_RATIO_SUM_DEFAULT = s
        Config.RANDOM_S_RATIO_SUM_CANDIDATES = []
        Config.RANDOM_S_RATIO_SUM_SEQUENCE = []
        r = run_one_setting(f"sum={s} (uniform)", args.time, args.cases)
        results_uniform.append(r)
        print_result(r)

    # 軸1-B: varied(ターゲットごとに候補から総和を選ぶ=深さがばらつく)
    print("\n【軸B: 総和をターゲットごとにばらつかせる(varied, 深さが多様)】")
    varied_sets = [grp for grp in args.varied_sets.split(";") if grp.strip()]
    results_varied = []
    for grp in varied_sets:
        cands = [int(x) for x in grp.split(",")]
        Config.RANDOM_S_RATIO_SUM_CANDIDATES = cands
        Config.RANDOM_S_RATIO_SUM_SEQUENCE = []
        r = run_one_setting(f"varied{cands}", args.time, args.cases)
        results_varied.append(r)
        print_result(r)

    # まとめ
    all_results = results_uniform + results_varied
    print("\n" + "=" * 64)
    print("  まとめ: 提案が卒論を改善したケース率と異重き候補数")
    print("=" * 64)
    print(f"  {'設定':<22} {'改善率':>8} {'異重き候補':>10}")
    for r in all_results:
        if r["tested"]:
            rate = 100 * r["prop_beats_thesis"] / r["tested"]
            print(f"  {r['label']:<22} {rate:>7.1f}% {r['avg_cand']:>10.1f}")
    print("=" * 64)
    print("  読み方: 総和を揃える(軸A)と深さが揃い異重き候補が少なめ、")
    print("          ばらつかせる(軸B)と深さが多様で異重きが効きやすい、")
    print("          という仮説をこの数字で検証できる。")

    # 出力(要約ファイル + グラフ)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("sum_results", f"sum_{ts}")
    os.makedirs(out_dir, exist_ok=True)

    # 要約ファイル
    rows = []
    for r in all_results:
        if not r["tested"]:
            rows.append([r["label"], 0, "-", "-", "-", "-", "-"])
            continue
        tot = r["tot"]
        rate = 100 * r["prop_beats_thesis"] / r["tested"]
        red_prop = 100 * (tot["orig"] - tot["proposed"]) / tot["orig"] if tot["orig"] else 0
        rows.append([
            r["label"], r["tested"],
            tot["orig"], tot["thesis"], tot["proposed"],
            f"{rate:.1f}%", f"{r['avg_cand']:.1f}",
        ])
    notes = [
        f"試薬{args.reagents}, 液滴{args.targets}, 各{args.cases}ケース, {args.time}秒",
        "軸A=総和を揃える(uniform), 軸B=総和をばらつかせる(varied)。",
        "改善率=提案が卒論より廃棄を減らしたケースの割合。",
        "異重き候補=生成された異重きピアの平均数(0なら異重きの出番なし)。",
        "総和固定+既約(gcd=1)はジェネレータ標準。",
    ]
    summary_path = os.path.join(out_dir, "summary.txt")
    save_summary(summary_path,
                 ["設定", "ケース数", "元MTWM", "卒論", "提案", "改善率", "異重き候補"],
                 rows, notes)
    # ★設定ごとの集計データをCSVでも保存
    csv_rows = []
    for r in all_results:
        if r["tested"]:
            csv_rows.append([
                r["label"], r["tested"],
                r["tot"]["orig"], r["tot"]["thesis"], r["tot"]["proposed"],
                r["prop_beats_thesis"],
                f"{100*r['prop_beats_thesis']/r['tested']:.1f}",
                f"{r['avg_cand']:.2f}", r["non_optimal"],
            ])
    save_csv(os.path.join(out_dir, "settings_summary.csv"),
             ["setting", "cases", "nw_orig", "nw_thesis", "nw_proposed",
              "prop_beats_thesis", "improve_rate_pct", "avg_hetero_cand", "non_optimal"],
             csv_rows)

    # グラフ1: 設定ごとの改善率
    valid = [r for r in all_results if r["tested"]]
    if valid:
        labels = [r["label"] for r in valid]
        rates = [100 * r["prop_beats_thesis"] / r["tested"] for r in valid]
        cands = [r["avg_cand"] for r in valid]
        draw_bar_chart(labels, [rates],
                       os.path.join(out_dir, "improvement_rate.png"),
                       title="Improvement rate (proposed beats thesis) by ratio-sum setting",
                       ylabel="Improvement rate (%)")
        # グラフ2: 設定ごとの異重き候補数
        draw_bar_chart(labels, [cands],
                       os.path.join(out_dir, "hetero_candidates.png"),
                       title="Avg. hetero-peer candidates by ratio-sum setting",
                       ylabel="Avg. candidates")
        # グラフ3: 3段階の総廃棄(設定別、3系列)
        orig = [r["tot"]["orig"] for r in valid]
        thesis = [r["tot"]["thesis"] for r in valid]
        prop = [r["tot"]["proposed"] for r in valid]
        draw_bar_chart(labels, [orig, thesis, prop],
                       os.path.join(out_dir, "waste_comparison.png"),
                       title="Total waste (nw) by ratio-sum setting",
                       ylabel="Total waste nw",
                       legend=["orig MTWM", "thesis (equal-weight)", "proposed (hetero)"])

    print(f"\n要約ファイル: {summary_path}")
    print(f"グラフ: {out_dir}/improvement_rate.png, hetero_candidates.png, waste_comparison.png")


if __name__ == "__main__":
    main()