#!/usr/bin/env python3
"""
解の「混ぜ方」と「各ノードの使われ方」を、読みやすいテキストで明示する。

図ではエッジが交差して追いにくいので、各ノードについて
  - 何を何単位混ぜて作られたか（入力）
  - 作った液滴がどこへ何単位供給されたか（出力先）
  - 廃棄量
を一覧表で示す。ピアは体積比も明示する。

使い方:
  python3 explain_solution.py --targets "11,28,15/3,3,3,2;19,8,45/4,3,3,2;5,1,30/4,3,3" --time 60
  または detail.txt を解析:
  python3 explain_solution.py --detail path/to/proposed_nolimit.txt
"""
import re
import io
import argparse
import contextlib
from collections import defaultdict


def parse_detail_file(path):
    """detail.txt を解析して、ノードごとの (比, 混合内容) を取り出す。"""
    text = open(path, encoding="utf-8").read()
    nodes = {}
    # [node_name] level=X 比=[...]  /  混合: ...
    blocks = re.findall(
        r"\[([^\]]+)\]\s*level=([\d.]+)\s*比=(\[[^\]]*\])\s*\n\s*混合:\s*([^\n]+)",
        text)
    for name, level, ratio, mix in blocks:
        nodes[name] = {
            "level": float(level),
            "ratio": ratio.strip(),
            "mix": mix.strip(),
        }
    # 総廃棄など
    waste = re.search(r"総廃棄 nw = (\d+)", text)
    return nodes, (waste.group(1) if waste else "?")


def analyze_usage(nodes):
    """各ノードの出力先(誰が何単位使ったか)を集計する。"""
    consumers = defaultdict(list)  # node -> [(consumer, count)]
    for name, info in nodes.items():
        # ピア名はハイフンを含むので [A-Za-z0-9_-] でマッチ
        for m in re.finditer(r"(\d+)\s*x\s*([A-Za-z0-9_-]+)", info["mix"]):
            cnt = int(m.group(1))
            src = m.group(2)
            consumers[src].append((name, cnt))
    return consumers


def describe_mix(mix):
    """混合内容を読みやすく。ピア名は体積比を添える。"""
    parts = []
    for m in re.finditer(r"(\d+)\s*x\s*([A-Za-z0-9_-]+)", mix):
        cnt, src = m.group(1), m.group(2)
        tag = ""
        if "_r21" in src:
            tag = " (体積比2:1)"
        elif "_r12" in src:
            tag = " (体積比1:2)"
        elif "_r11" in src:
            tag = " (体積比1:1)"
        parts.append(f"{src}{tag} ×{cnt}")
    return " + ".join(parts)


def main():
    ap = argparse.ArgumentParser(description="解の混ぜ方と使われ方を明示")
    ap.add_argument("--detail", type=str, help="detail.txt のパス")
    args = ap.parse_args()

    if not args.detail:
        print("--detail で detail.txt を指定してください")
        return

    nodes, total_waste = parse_detail_file(args.detail)
    consumers = analyze_usage(nodes)

    print("=" * 72)
    print(f"  解の混ぜ方と使われ方  (総廃棄 nw={total_waste})")
    print("=" * 72)

    # レベル順(浅い→深い)に並べる
    for name in sorted(nodes, key=lambda n: (nodes[n]["level"], n)):
        info = nodes[name]
        is_peer = "peer" in name.lower()
        is_root = info["level"] == 0
        kind = "【ピア】" if is_peer else ("【ルート/目標】" if is_root else "【ミキサー】")
        # 体積比(ピア)
        vol = ""
        if "_r21" in name:
            vol = " 体積比2:1"
        elif "_r12" in name:
            vol = " 体積比1:2"
        elif "_r11" in name:
            vol = " 体積比1:1"

        print(f"\n{kind} {name}{vol}")
        print(f"  比 {info['ratio']}")
        print(f"  ← 作り方: {describe_mix(info['mix'])}")

        # この液滴がどこへ行ったか
        if name in consumers:
            dests = consumers[name]
            total_used = sum(c for _, c in dests)
            dest_str = ", ".join(f"{d}へ{c}単位" for d, c in dests)
            print(f"  → 使われ方: {dest_str}  (計{total_used}単位)")
        elif is_root:
            print(f"  → 使われ方: 最終目標(出力)")
        else:
            print(f"  → 使われ方: (どこにも供給されず=全量廃棄の可能性)")

    print("\n" + "=" * 72)
    print("  ※ピアの『作り方』の単位数が体積比(2:1なら2単位+1単位)")
    print("  ※『使われ方』の単位数の合計が、そのノードの出力供給量")
    print("  ※作った量 - 使われた量 = 廃棄")
    print("=" * 72)


if __name__ == "__main__":
    main()