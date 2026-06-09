import os
import sys
import math
import copy
import networkx as nx
import matplotlib.pyplot as plt

# プロジェクトルートへのパスを通す
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 実行環境にモジュールがない場合のダミーデータ（動作確認用）
try:
    from core.algorithm.dfmm import find_factors_for_sum
    from scenarios import TARGETS_FOR_AUTO_MODE, TARGETS_FOR_MANUAL_MODE
except ImportError:
    print("Warning: 'core' or 'scenarios' module not found. Using dummy data for demo.")
    def find_factors_for_sum(s, m): return [2, 2] if s <= 4 else [3, 2]
    TARGETS_FOR_MANUAL_MODE = [{'name': 'Test_Target', 'ratios': [1, 2, 1], 'factors': [2, 2]}]
    TARGETS_FOR_AUTO_MODE = []

# 設定
OUTPUT_DIR = "dfmm_uniqueness_graphs"
MAX_MIXER_SIZE = 5

# 描画用設定
STYLE = {
    "unique":   {"color": "#87CEEB", "label": "UNIQUE (Fixed)"},       # 水色
    "ambiguous":{"color": "#FF6347", "label": "AMBIGUOUS (Needs Search)"}, # トマト色
    "root":     {"color": "#98FB98", "label": "TARGET (Root)"},       # 薄緑
}

def save_text_report(save_dir, target_name, report_lines):
    """分析結果をテキストファイルとして保存する"""
    filename = f"{target_name.replace(' ', '_')}_report.txt"
    filepath = os.path.join(save_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        f.write("\n\n=== End of Report ===\n")
    
    print(f" -> Text Report Saved: {filename}")

def analyze_and_visualize(target_config, config_name):
    """
    ターゲット1つ分のDFMMツリーを構築し、画像とテキストレポートを出力する。
    """
    name = target_config.get('name', 'Unknown')
    ratios = target_config['ratios']
    factors = target_config.get('factors')
    
    if not factors:
        print(f"Skipping {name}: No factors.")
        return

    print(f"Visualizing: {name} ...")
    
    G = nx.DiGraph()
    report_lines = [] 
    
    # --- ヘッダー情報の作成 (ここを追加・修正) ---
    report_lines.append(f"=== DFMM Reagent Allocation Report: {name} ===")
    report_lines.append(f"Target Name    : {name}")
    report_lines.append(f"Original Ratios: {ratios}")  # <--- ここに濃度比を追加
    report_lines.append(f"Mixing Factors : {factors}")
    report_lines.append("-" * 50)
    report_lines.append("")
    
    num_levels = len(factors)
    values_to_process = list(ratios)
    
    # (level, index) のリスト。下のレベルから順に構築。
    child_node_ids = [] 

    # --- DFMMシミュレーション & グラフ構築 ---
    for level in range(num_levels - 1, -1, -1):
        current_factor = factors[level]
        
        report_lines.append(f"--- Level {level} (Factor: {current_factor}) ---")
        
        # 1. このレベルの計算
        level_remainders = [v % current_factor for v in values_to_process]
        level_quotients = [v // current_factor for v in values_to_process]
        
        total_inputs = sum(level_remainders) + len(child_node_ids)
        num_nodes = math.ceil(total_inputs / current_factor) if total_inputs > 0 else 0
        
        # 試薬プールの情報
        active_reagents_indices = [i for i, val in enumerate(level_remainders) if val > 0]
        num_active_reagent_types = len(active_reagents_indices)
        
        # テキスト用に試薬在庫の文字列表現を作成
        reagent_inventory_str = ", ".join([f"R{i}(qty:{val})" for i, val in enumerate(level_remainders) if val > 0])
        report_lines.append(f"  Available Reagents Pool: [{reagent_inventory_str}]")

        # 一意性判定のための準備
        nodes_needing_reagents = []
        node_capacities = []
        
        for k in range(num_nodes):
            # 子ノード数 (ラウンドロビン割り当て)
            if num_nodes > 0:
                num_children = (len(child_node_ids) // num_nodes) + (1 if k < (len(child_node_ids) % num_nodes) else 0)
            else:
                num_children = 0
            
            slots_needed = current_factor - num_children
            node_capacities.append(slots_needed)
            if slots_needed > 0:
                nodes_needing_reagents.append(k)

        # 2. ノードの作成と判定
        current_level_node_ids = []
        for k in range(num_nodes):
            node_id = f"L{level}_K{k}"
            current_level_node_ids.append(node_id)
            
            slots_needed = node_capacities[k]
            is_unique = False
            status = "ambiguous"
            note_for_graph = ""
            text_report_detail = ""

            # --- ステータス判定 ---
            if level == 0:
                status = "root"
                is_unique = True
                text_report_detail = "ROOT NODE (Final Output)"
            elif slots_needed == 0:
                is_unique = True
                status = "unique"
                note_for_graph = "Full"
                text_report_detail = "Full from children (No Reagents needed)"
            
            # 試薬が必要な場合
            else:
                # ロジック判定
                if len(nodes_needing_reagents) == 1 and k in nodes_needing_reagents:
                    # このノードだけが試薬を必要とする -> 残り全部ここに来る
                    is_unique = True
                    status = "unique"
                    note_for_graph = "Sole Receiver"
                    reagents_str = ", ".join([f"R{i}" for i in active_reagents_indices])
                    text_report_detail = f"FIXED: Takes all available reagents ({reagents_str}) -> Needs {slots_needed} slots"
                    
                elif num_active_reagent_types <= 1:
                    # 試薬の種類が1つしかない -> 確定
                    is_unique = True
                    status = "unique"
                    note_for_graph = "Mono-Reagent"
                    r_idx = active_reagents_indices[0] if active_reagents_indices else "?"
                    text_report_detail = f"FIXED: Only R{r_idx} is available -> Needs {slots_needed} slots"
                    
                else:
                    # 複数種類あり、かつ複数のノードが欲しがっている -> 探索が必要
                    is_unique = False
                    status = "ambiguous"
                    note_for_graph = "Needs Decision"
                    candidates = ", ".join([f"R{i}" for i in active_reagents_indices])
                    text_report_detail = f"AMBIGUOUS: Needs {slots_needed} slots. Candidates from: [{candidates}]"

            # グラフ用ノード追加
            label = f"{node_id}\n(F={current_factor})\n{note_for_graph}"
            G.add_node(node_id, label=label, level=level, status=status, k=k)

            # レポートに行を追加
            report_lines.append(f"  Node {node_id}: {text_report_detail}")

        # エッジ接続処理 (子 -> 親)
        if child_node_ids:
            parent_idx_counter = 0
            for child_id in child_node_ids:
                parent_id = current_level_node_ids[parent_idx_counter]
                G.add_edge(child_id, parent_id)
                parent_idx_counter = (parent_idx_counter + 1) % num_nodes

        # 次のレベルへ
        child_node_ids = current_level_node_ids
        values_to_process = level_quotients
        report_lines.append("") # 空行で見やすく

    # --- 保存処理 ---
    save_dir = os.path.join(OUTPUT_DIR, config_name)
    os.makedirs(save_dir, exist_ok=True)

    # 1. グラフ描画
    draw_graph(G, name, save_dir)
    
    # 2. テキストレポート出力
    save_text_report(save_dir, name, report_lines)

def draw_graph(G, target_name, save_dir):
    """NetworkXのグラフを描画して保存（シンプル版）"""
    if len(G.nodes) == 0:
        return

    pos = {}
    levels = sorted(list(set(nx.get_node_attributes(G, 'level').values())), reverse=True)
    
    level_nodes = {}
    for n, data in G.nodes(data=True):
        l = data['level']
        if l not in level_nodes: level_nodes[l] = []
        level_nodes[l].append(n)
        
    for l in levels:
        nodes = sorted(level_nodes[l], key=lambda x: G.nodes[x]['k'])
        width = len(nodes)
        for i, n in enumerate(nodes):
            pos[n] = (i - (width - 1) / 2, -l)

    plt.figure(figsize=(12, 8))
    ax = plt.gca()
    
    # ノード色の決定
    node_colors = []
    for n in G.nodes():
        status = G.nodes[n]['status']
        node_colors.append(STYLE[status]['color'])
        
    # ノード描画
    nx.draw_networkx_nodes(G, pos, node_size=2500, node_color=node_colors, edgecolors="black")
    nx.draw_networkx_edges(G, pos, arrowsize=20, edge_color="gray")
    
    # ラベル描画
    labels = nx.get_node_attributes(G, 'label')
    nx.draw_networkx_labels(G, pos, labels, font_size=9, font_weight="bold")
    
    # 凡例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', label=STYLE['root']['label'], markerfacecolor=STYLE['root']['color'], markersize=15),
        Line2D([0], [0], marker='o', color='w', label=STYLE['unique']['label'], markerfacecolor=STYLE['unique']['color'], markersize=15),
        Line2D([0], [0], marker='o', color='w', label=STYLE['ambiguous']['label'], markerfacecolor=STYLE['ambiguous']['color'], markersize=15),
    ]
    ax.legend(handles=legend_elements, loc='upper right')

    plt.title(f"DFMM Analysis: {target_name}", fontsize=16)
    plt.axis('off')
    
    filename = f"{target_name.replace(' ', '_')}_graph.png"
    plt.savefig(os.path.join(save_dir, filename), dpi=150, bbox_inches="tight")
    plt.close()
    print(f" -> Graph Saved: {filename}")

def main():
    print("--- Visualizing DFMM Node Uniqueness & Text Report ---")
    
    # 1. Manual Targets
    print("\n[Manual Mode Targets]")
    for t in TARGETS_FOR_MANUAL_MODE:
        analyze_and_visualize(t, "Manual_Targets")

    # 2. Auto Targets
    print("\n[Auto Mode Targets]")
    auto_targets = copy.deepcopy(TARGETS_FOR_AUTO_MODE)
    for t in auto_targets:
        if 'factors' not in t:
            s = sum(t['ratios'])
            f = find_factors_for_sum(s, MAX_MIXER_SIZE)
            if f is None: continue
            t['factors'] = f
        analyze_and_visualize(t, "Auto_Targets")

    print(f"\nAll files saved to '{OUTPUT_DIR}' directory.")

if __name__ == "__main__":
    main()