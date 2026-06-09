"""
異重きピア(hetero-weight peer)と混合比の使用状況を集計・記録するユーティリティ。

solve 後に collect_hetero_usage(solver) を呼ぶと、その解で
- 異重きピアが何個生成され、何個使われたか
- どの体積比(1:1, 2:1, 1:2 ...)が何回使われたか
- 各使用ピアの詳細(入力重み・出力重み・比)
を集計して dict で返す。append_usage_log(...) でファイルに追記できる。
"""
import os
from datetime import datetime


def collect_hetero_usage(solver):
    """solve 済みの solver から異重きピアの使用状況を集計して返す。"""
    generated = 0          # 生成された異重きピア候補数
    used = 0               # 実際に活性化した異重きピア数
    ratio_used = {}        # 体積比ごとの使用回数 例 {"1:1": 3, "2:1": 1}
    ratio_generated = {}   # 体積比ごとの生成数
    used_details = []      # 使われたピアの詳細

    for pn in solver.peer_vars:
        is_hetero = pn.get("is_hetero", False) or "peer_gen" in pn.get("name", "")
        if not is_hetero:
            continue
        generated += 1
        ra = pn.get("ratio_a", 1)
        rb = pn.get("ratio_b", 1)
        ratio_key = f"{ra}:{rb}"
        ratio_generated[ratio_key] = ratio_generated.get(ratio_key, 0) + 1

        # 活性化したか
        try:
            active = solver.solver.Value(pn["is_active_var"]) == 1
        except Exception:
            active = False
        if active:
            used += 1
            ratio_used[ratio_key] = ratio_used.get(ratio_key, 0) + 1
            used_details.append({
                "name": pn.get("name", "?"),
                "weight_a": pn.get("weight_a"),
                "weight_b": pn.get("weight_b"),
                "p_new": pn.get("p_value"),
                "ratio": ratio_key,
            })

    return {
        "generated": generated,
        "used": used,
        "ratio_generated": ratio_generated,
        "ratio_used": ratio_used,
        "used_details": used_details,
    }


def format_usage(usage, header=None):
    """使用状況を読みやすい文字列にする。"""
    lines = []
    if header:
        lines.append(header)
    lines.append(f"  異重きピア: 生成 {usage['generated']}個 / 使用 {usage['used']}個")
    if usage["ratio_generated"]:
        gen = ", ".join(f"{k}={v}" for k, v in sorted(usage["ratio_generated"].items()))
        lines.append(f"  体積比ごとの生成数: {gen}")
    if usage["ratio_used"]:
        use = ", ".join(f"{k}={v}" for k, v in sorted(usage["ratio_used"].items()))
        lines.append(f"  体積比ごとの使用数: {use}")
    else:
        lines.append("  体積比ごとの使用数: (使用なし)")
    for d in usage["used_details"]:
        lines.append(f"    - {d['name']}: 重み{d['weight_a']}×{d['weight_b']} "
                     f"→出力{d['p_new']} (比{d['ratio']})")
    return "\n".join(lines)


def append_usage_log(usage, log_path, case_label=""):
    """使用状況をログファイルに追記する。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n[{ts}] {case_label}\n")
        f.write(format_usage(usage) + "\n")


def summarize_batch(usages):
    """複数ケースの usage リストを集計して全体傾向を返す。"""
    total_gen = sum(u["generated"] for u in usages)
    total_used = sum(u["used"] for u in usages)
    cases_with_use = sum(1 for u in usages if u["used"] > 0)
    ratio_total = {}
    for u in usages:
        for k, v in u["ratio_used"].items():
            ratio_total[k] = ratio_total.get(k, 0) + v
    return {
        "n_cases": len(usages),
        "total_generated": total_gen,
        "total_used": total_used,
        "cases_with_use": cases_with_use,
        "ratio_total_used": ratio_total,
    }


def format_batch_summary(batch):
    """バッチ集計を読みやすい文字列にする。"""
    lines = ["=" * 56, "  異重きピア・混合比の使用状況サマリ", "=" * 56]
    lines.append(f"  対象ケース数            : {batch['n_cases']}")
    lines.append(f"  異重きピアを使ったケース: {batch['cases_with_use']} "
                 f"({100*batch['cases_with_use']/batch['n_cases']:.1f}%)"
                 if batch["n_cases"] else "")
    lines.append(f"  異重きピア総生成数      : {batch['total_generated']}")
    lines.append(f"  異重きピア総使用数      : {batch['total_used']}")
    if batch["ratio_total_used"]:
        lines.append("  体積比ごとの総使用数:")
        for k, v in sorted(batch["ratio_total_used"].items()):
            share = 100 * v / batch["total_used"] if batch["total_used"] else 0
            lines.append(f"    比 {k}: {v}回 ({share:.0f}%)")
    else:
        lines.append("  体積比ごとの総使用数: (異重きピアの使用なし)")
    lines.append("=" * 56)
    return "\n".join(lines)