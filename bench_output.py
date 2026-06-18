"""
ベンチマーク/スキャンの結果を検証するための出力ユーティリティ。
  - save_summary(...)    : 結果を要約したテキストファイルを出力
  - draw_solution_tree(...) : 解(nodes_details + ピア)を木グラフ画像(PNG)に描画
  - draw_bar_chart(...)  : 設定ごとの結果を棒グラフ画像(PNG)に描画

解が本当に正しく構成されているか（どのノードが何を混ぜ、ピアがどこで使われ、
廃棄がどこに出たか）を目で確認できるようにする。
"""
import os
from datetime import datetime


def save_csv(path, header, rows):
    """全ケースの生データをCSVで保存する。集計はここから作り直せる。
    header: 列名のリスト, rows: 各行(リスト)のリスト。
    """
    import csv
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for r in rows:
            writer.writerow(r)
    return path


def save_summary(path, header, rows, notes=None, command=None):
    """結果要約をテキストファイルに保存。
    header: 列名のリスト, rows: 各行(リスト)のリスト, notes: 末尾の補足行リスト。
    command: 実行コマンド文字列。None なら sys.argv から自動取得する。
    """
    import sys
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if command is None:
        # 実行コマンドを自動取得(python3 スクリプト名 引数...)
        command = "python3 " + " ".join(sys.argv)
    # 列幅を揃える
    cols = [header] + [[str(c) for c in r] for r in rows]
    widths = [max(len(row[i]) for row in cols) for i in range(len(header))]
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# ベンチマーク結果要約  ({ts})\n\n")
        f.write(f"## 実行コマンド\n{command}\n\n")  # ★どのコマンドで実行したか記録
        f.write("  ".join(h.ljust(widths[i]) for i, h in enumerate(header)) + "\n")
        f.write("  ".join("-" * widths[i] for i in range(len(header))) + "\n")
        for r in rows:
            f.write("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)) + "\n")
        if notes:
            f.write("\n")
            for n in notes:
                f.write(n + "\n")
    return path


def draw_solution_tree(analysis, path, title=""):
    """解の analysis から木グラフを描いて PNG 保存する。
    エッジ重み(供給量)、各ノードの廃棄、試薬投入、ノードの役割を表示する。
    matplotlib と networkx が必要。失敗しても例外を投げず False を返す。
    """
    try:
        import networkx as nx
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import re
    except Exception as e:
        print(f"[可視化スキップ] networkx/matplotlib が必要: {e}")
        return False

    try:
        G = nx.DiGraph()
        node_labels = {}
        details = analysis.get("nodes_details", [])
        name_to_detail = {d.get("name"): d for d in details}

        # ノード追加。ラベルに 比・重み・廃棄 を表示
        for d in details:
            name = d.get("name", "?")
            ratio = d.get("ratio_composition", [])
            p_val = d.get("p_value")
            waste = d.get("waste", 0)
            is_peer = d.get("is_peer", False) or "peer" in str(name).lower()
            is_root = d.get("is_root", False)
            level = d.get("level", 0)
            # 短い名前(末尾)とラベル
            short = name.replace("mixer_", "").replace("peer_gen_", "P:").replace("peer_mixer_", "PM:")
            label = f"{short}\n{ratio}"
            if p_val is not None:
                label += f" w{p_val}"
            if waste and waste > 0:
                label += f"\nwaste{waste}"  # 廃棄があるノードは明示
            G.add_node(name, level=level, is_peer=is_peer, is_root=is_root,
                       waste=waste or 0)
            node_labels[name] = label

        # エッジ: mixing_str から「個数 x ノード名」を抽出し、重み付きで結ぶ
        node_names = set(G.nodes())
        edge_labels = {}
        reagent_inputs = {}  # ノード -> [(試薬名, 個数)]
        for d in details:
            name = d.get("name", "?")
            mix = d.get("mixing_str", "") or ""
            # "2 x mixer_xxx" や "1 x Reagent3" を抽出(ピア名はハイフンを含む)
            for m in re.finditer(r"(\d+)\s*x\s*([A-Za-z0-9_-]+)", mix):
                cnt = int(m.group(1))
                src = m.group(2)
                if src in node_names and src != name:
                    G.add_edge(src, name, weight=cnt)
                    edge_labels[(src, name)] = str(cnt)  # エッジ重み=供給量
                elif src.lower().startswith("reagent") or src.startswith("R"):
                    reagent_inputs.setdefault(name, []).append((src, cnt))

        if G.number_of_nodes() == 0:
            print("[可視化スキップ] 解にノードがありません")
            return False

        # ★ピアノードのラベルに「出力先(どこへ何単位)」を文字で追記。
        # エッジが図で追いにくくても、ノードを見れば使われ先が分かるように。
        def short_name(nm):
            return nm.replace("mixer_", "").replace("peer_gen_", "P:").replace("peer_mixer_", "PM:")
        for d in details:
            name = d.get("name", "?")
            is_peer = d.get("is_peer", False) or "peer" in str(name).lower()
            if not is_peer:
                continue
            outs = [(v, G[name][v].get("weight", 1)) for v in G.successors(name)]
            if outs:
                dest_str = ", ".join(f"{short_name(v)}x{w}" for v, w in outs)
                node_labels[name] = node_labels.get(name, name) + f"\n->used by: {dest_str}"
            else:
                node_labels[name] = node_labels.get(name, name) + "\n->used by: NONE"

        # 試薬を独立ノードとして追加(緑の小ノード)
        reagent_node_set = []
        for tgt, rlist in reagent_inputs.items():
            for (rname, cnt) in rlist:
                rnode = f"{rname}->{tgt}"
                G.add_node(rnode, level=name_to_detail.get(tgt, {}).get("level", 0) + 0.5,
                           is_reagent=True)
                node_labels[rnode] = rname
                G.add_edge(rnode, tgt, weight=cnt)
                edge_labels[(rnode, tgt)] = str(cnt)
                reagent_node_set.append(rnode)

        # レイアウト: ターゲットごとに横の帯域を分け、レベルで縦に整列。
        # これでツリーごとに縦のまとまりができ、エッジ交差が減る。
        import re as _re

        def target_of(node_name):
            """ノード名から target_id を推定。mixer_t0_... → 0。ピアは source_a 側。"""
            m = _re.search(r"_t(\d+)_", node_name)
            if m:
                return int(m.group(1))
            # ピア名 peer_..._t0l1k0-t1l1k0 → 最初の tN
            m = _re.search(r"t(\d+)l", node_name)
            if m:
                return int(m.group(1))
            return 0

        pos = {}
        non_reagent = [(n, d) for n, d in G.nodes(data=True) if not d.get("is_reagent")]
        # ターゲットごと・レベルごとにグループ化
        groups = {}  # (target, level) -> [nodes]
        targets_seen = set()
        for n, data in non_reagent:
            t = target_of(n)
            lv = data.get("level", 0)
            targets_seen.add(t)
            groups.setdefault((t, lv), []).append(n)
        targets_sorted = sorted(targets_seen)
        # 各ターゲットに横の基準位置を割り当て(十分広く離す)
        TARGET_WIDTH = 14.0   # ターゲット間の横間隔
        X_GAP = 3.2           # 同一(target,level)内のノード間隔
        Y_GAP = 2.6           # レベル間の縦間隔
        target_base = {t: i * TARGET_WIDTH for i, t in enumerate(targets_sorted)}
        for (t, lv), ns in groups.items():
            ns_sorted = sorted(ns)
            base = target_base[t]
            for i, n in enumerate(ns_sorted):
                x = base + (i - (len(ns_sorted) - 1) / 2.0) * X_GAP
                pos[n] = (x, -lv * Y_GAP)
        # 試薬ノードは供給先の真下に
        reagent_by_target = {}
        for n, data in G.nodes(data=True):
            if data.get("is_reagent"):
                succ = list(G.successors(n))
                tgt = succ[0] if succ else None
                reagent_by_target.setdefault(tgt, []).append(n)
        for tgt, rns in reagent_by_target.items():
            if tgt in pos:
                tx, ty = pos[tgt]
            else:
                tx, ty = 0, 0
            for j, rn in enumerate(rns):
                pos[rn] = (tx + (j - (len(rns) - 1) / 2.0) * 1.3, ty - Y_GAP * 0.5)

        # 色分け: ルート=濃緑, ピア=橙, 試薬=薄緑, 廃棄ありノード=赤縁, 通常=青
        node_colors = []
        edge_cols = []
        for n, data in G.nodes(data=True):
            if data.get("is_reagent"):
                node_colors.append("#B8E0B8")
            elif data.get("is_root"):
                node_colors.append("#7BC47B")
            elif data.get("is_peer"):
                node_colors.append("#E8A87C")
            else:
                node_colors.append("#A0C4D8")
            # 廃棄があるノードは赤い縁取り
            edge_cols.append("red" if data.get("waste", 0) > 0 else "black")

        n_nodes = G.number_of_nodes()
        n_targets = len(targets_sorted)
        n_levels = len(set(lv for _, lv in [(n, d.get("level", 0)) for n, d in G.nodes(data=True)]))
        fig_w = max(14, n_targets * 6.5)
        fig_h = max(9, n_levels * 2.0)
        plt.figure(figsize=(fig_w, fig_h))
        nx.draw_networkx_nodes(G, pos, node_size=2400,
                               node_color=node_colors, edgecolors=edge_cols,
                               linewidths=[2.5 if c == "red" else 1 for c in edge_cols])
        # エッジを2種類に分ける:
        #  - ピアが供給元のエッジ(=ピアが使われる方向) → オレンジ・太め・曲線で強調
        #  - それ以外(通常の混合) → 灰色・直線
        peer_out_edges = []
        normal_edges = []
        for u, v in G.edges():
            if G.nodes[u].get("is_peer"):
                peer_out_edges.append((u, v))
            else:
                normal_edges.append((u, v))
        # 通常エッジ
        nx.draw_networkx_edges(G, pos, edgelist=normal_edges,
                               arrowstyle="-|>", arrowsize=20,
                               edge_color="#777777", width=1.3,
                               node_size=2400, min_source_margin=18,
                               min_target_margin=18)
        # ピアの出力エッジ(使われ先)= 強調。曲線で他と分離。
        nx.draw_networkx_edges(G, pos, edgelist=peer_out_edges,
                               arrowstyle="-|>", arrowsize=26,
                               edge_color="#E8730C", width=2.4,
                               node_size=2400, min_source_margin=18,
                               min_target_margin=18,
                               connectionstyle="arc3,rad=0.15")
        nx.draw_networkx_labels(G, pos, node_labels, font_size=7)
        # エッジ重み(供給量)を表示。向きと重なりにくいよう位置調整。
        nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=8,
                                     font_color="darkblue", label_pos=0.6,
                                     bbox=dict(boxstyle="round,pad=0.1",
                                               fc="white", ec="none", alpha=0.7))

        # 凡例
        import matplotlib.lines as mlines
        legend_items = [
            mpatches.Patch(color="#7BC47B", label="Root (target output)"),
            mpatches.Patch(color="#A0C4D8", label="Mixer node"),
            mpatches.Patch(color="#E8A87C", label="Peer node (sharing/hetero-mix)"),
            mpatches.Patch(color="#B8E0B8", label="Reagent input"),
            mpatches.Patch(facecolor="white", edgecolor="red", linewidth=2.5,
                           label="Red border = has waste"),
            mlines.Line2D([], [], color="#E8730C", linewidth=2.4,
                          label="Orange edge = peer is USED here (peer output)"),
        ]
        plt.legend(handles=legend_items, loc="upper left", fontsize=8)
        total_waste = analysis.get("total_waste", "?")
        plt.title((title or "Solution Tree") +
                  f"  [total waste={total_waste}]  arrow: supplier->consumer, number: supply amount")
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        return True
    except Exception as e:
        print(f"[可視化失敗] {e}")
        import traceback
        traceback.print_exc()
        return False


def save_solution_detail(path, analysis, label=""):
    """解の詳細(各ノードが何を混ぜたか、廃棄、ピア使用)をテキストで保存。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 解の詳細  {label}\n\n")
        f.write(f"総廃棄 nw = {analysis.get('total_waste')}\n")
        f.write(f"総試薬 nr = {analysis.get('total_reagent_units')}\n")
        f.write(f"総混合操作 = {analysis.get('total_operations')}\n")
        f.write(f"ソルバー状態 = {analysis.get('solver_status', '?')}\n\n")
        f.write("各ノードの構成:\n")
        for d in analysis.get("nodes_details", []):
            f.write(f"  [{d.get('name')}] level={d.get('level')} "
                    f"比={d.get('ratio_composition')}\n")
            mix = d.get("mixing_str")
            if mix:
                f.write(f"      混合: {mix}\n")
    return path


def draw_bar_chart(labels, series, path, title="", ylabel="", legend=None):
    """棒グラフを描いて PNG 保存する。
    labels: X軸のラベル(設定名)のリスト。
    series: 系列のリスト。各系列は labels と同じ長さの数値リスト。
            1系列なら [[...]], 複数系列なら [[...],[...]]。
    legend: 各系列の名前(複数系列のとき)。
    失敗しても例外を投げず False を返す。
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception as e:
        print(f"[グラフスキップ] matplotlib が必要: {e}")
        return False
    try:
        n_series = len(series)
        n_groups = len(labels)
        x = np.arange(n_groups)
        width = 0.8 / max(1, n_series)
        plt.figure(figsize=(max(7, n_groups * 1.2), 5))
        colors = ["#4C78A8", "#E8A87C", "#5B9279", "#C45B5B", "#9A8FB8"]
        for i, ys in enumerate(series):
            offset = (i - (n_series - 1) / 2.0) * width
            label = legend[i] if legend and i < len(legend) else None
            bars = plt.bar(x + offset, ys, width, label=label,
                           color=colors[i % len(colors)], edgecolor="black", linewidth=0.5)
            for b, y in zip(bars, ys):
                plt.text(b.get_x() + b.get_width() / 2, b.get_height(),
                         f"{y:g}", ha="center", va="bottom", fontsize=8)
        plt.xticks(x, labels, rotation=20, ha="right")
        plt.ylabel(ylabel)
        plt.title(title)
        if legend:
            plt.legend()
        plt.tight_layout()
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        return True
    except Exception as e:
        print(f"[グラフ失敗] {e}")
        return False