import os
import sys
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

# --- パス解決 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)
# --------------------

# 既存モジュールのインポート
from utils.config_loader import Config
from utils import create_dfmm_node_name
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.model.problem import MTWMProblem
from scenarios import TARGETS_FOR_MANUAL_MODE, TARGETS_FOR_AUTO_MODE
from core.algorithm.dfmm import apply_auto_factors

class StructureVisualizer:
    """
    問題構造(MTWMProblem)を受け取り、その「候補エッジ」をネットワーク図として可視化するクラス。
    """
    # スタイル設定
    STYLE_CONFIG = {
        "mix_node": {"color": "#87CEEB", "size": 2000},
        "target_node": {"color": "#90EE90", "size": 2000},
        "mix_peer_node": {"color": "#FFB6C1", "size": 1800},
        "reagent_node": {"color": "#FFDAB9", "size": 1500},
        "default_node": {"color": "gray", "size": 1000},
        "edge_default": {"color": "black", "width": 2.0, "style": "solid"},
        "edge_potential": {"color": "purple", "width": 1.0, "style": "dashed", "alpha": 0.6},
        "edge_reagent": {"color": "#FFA500", "width": 1.0, "style": "dotted"},
        "font": {"font_size": 10, "font_weight": "bold", "font_color": "black"},
    }
    
    LAYOUT_CONFIG = {
        "x_gap": 6.0, "y_gap": 5.0, "tree_gap": 10.0, 
    }

    def __init__(self, problem, tree_structures):
        self.problem = problem
        self.tree_structures = tree_structures

    def generate_graph(self, mode="full"):
        """
        Graphオブジェクトを構築する
        mode: "basic" (DFMM構造のみ) or "full" (共有候補含む)
        """
        G = nx.DiGraph()
        
        # 1. 必須接続(Default Connections)の特定
        default_connections = set()
        for t_idx, tree in enumerate(self.tree_structures):
            for (p_lvl, p_idx), data in tree.items():
                for (c_lvl, c_idx) in data['children']:
                    dst = (t_idx, p_lvl, p_idx)
                    src = (t_idx, c_lvl, c_idx)
                    default_connections.add((dst, src))

        # 2. ノードの追加 (DFMM Nodes)
        for t_idx, tree in enumerate(self.problem.forest):
            for level, nodes in tree.items():
                for n_idx, _ in enumerate(nodes):
                    node_name = create_dfmm_node_name(t_idx, level, n_idx)
                    p_val = self.problem.p_value_maps[t_idx].get((level, n_idx), "?")
                    
                    label = f"T{t_idx+1}\n(P={p_val})"
                    if level == 0:
                        label = f"Target {t_idx+1}\n(Root)"
                        
                    G.add_node(node_name, label=label, level=level, target=t_idx, type="mix")
                    
                    # 試薬ノードとエッジの追加 (Reagent Edges)
                    num_reagents = self.problem.num_reagents
                    for r_idx in range(num_reagents):
                        r_name = f"R_dummy_{node_name}_{r_idx}"
                        G.add_node(r_name, label=f"R{r_idx+1}", level=level+0.8, target=t_idx, type="reagent")
                        G.add_edge(r_name, node_name, type="reagent")

        # 3. ノードの追加 (Peer Nodes) [Modified]
        if mode == "full":
            for i, peer in enumerate(self.problem.peer_nodes):
                p_name = peer["name"]
                
                # --- [分岐] Dynamic vs Fixed ---
                if peer.get("is_generic", False):
                    # Dynamic Peer
                    candidates = peer["candidate_sources"]
                    
                    # 可視化位置（レベル）の計算: 候補の平均位置の少し上
                    if candidates:
                        avg_level = sum(c[1] for c in candidates) / len(candidates) - 0.5
                        target_idx = candidates[0][0] # 便宜上、最初の候補のターゲットIDを使用
                    else:
                        avg_level = 0.5
                        target_idx = 0
                    
                    G.add_node(p_name, label=f"Peer\n(P={peer['p_value']})", level=avg_level, target=target_idx, type="mix_peer")
                    
                    # 候補ノードからのエッジを追加 (タイプは potential)
                    for src in candidates:
                        src_name = create_dfmm_node_name(*src)
                        G.add_edge(src_name, p_name, type="potential")
                        
                else:
                    # Fixed Peer (Legacy)
                    src_a = peer["source_a_id"]
                    src_b = peer["source_b_id"]
                    avg_level = (src_a[1] + src_b[1]) / 2.0 - 0.5
                    
                    G.add_node(p_name, label=f"Peer\n(P={peer['p_value']})", level=avg_level, target=src_a[0], type="mix_peer")
                    
                    src_a_name = create_dfmm_node_name(*src_a)
                    src_b_name = create_dfmm_node_name(*src_b)
                    # 固定入力エッジ (タイプは default)
                    G.add_edge(src_a_name, p_name, type="default") 
                    G.add_edge(src_b_name, p_name, type="default")

        # 4. エッジの追加 (DFMMへの入力)
        for dst_key, sources in self.problem.potential_sources_map.items():
            dst_name = create_dfmm_node_name(*dst_key)
            
            for src in sources:
                src_target, src_level, src_node = src
                
                if src_target == "R":
                    if mode == "full":
                        src_name = self.problem.peer_nodes[src_level]["name"]
                        G.add_edge(src_name, dst_name, type="potential")
                    continue
                
                src_name = create_dfmm_node_name(src_target, src_level, src_node)
                is_default = (dst_key, src) in default_connections
                
                if is_default:
                    G.add_edge(src_name, dst_name, type="default")
                elif mode == "full":
                    G.add_edge(src_name, dst_name, type="potential")

        return G

    def draw_and_save(self, G, output_path, title):
        pos = self._calculate_node_positions(G)
        
        plt.figure(figsize=(20, 12))
        ax = plt.gca()
        
        # ノード描画
        for node_type in ["mix", "target_node", "mix_peer", "reagent"]:
            style_key = "mix_node"
            if node_type == "reagent": style_key = "reagent_node"
            elif node_type == "mix_peer": style_key = "mix_peer_node"
            
            nodelist = [n for n, d in G.nodes(data=True) if d.get("type") == node_type]
            if not nodelist: continue

            if node_type == "mix":
                target_nodes = [n for n in nodelist if G.nodes[n].get("level") == 0]
                mix_nodes = [n for n in nodelist if G.nodes[n].get("level") != 0]
                nx.draw_networkx_nodes(G, pos, nodelist=target_nodes, node_color=self.STYLE_CONFIG["target_node"]["color"], node_size=self.STYLE_CONFIG["target_node"]["size"], ax=ax, edgecolors="black")
                nx.draw_networkx_nodes(G, pos, nodelist=mix_nodes, node_color=self.STYLE_CONFIG["mix_node"]["color"], node_size=self.STYLE_CONFIG["mix_node"]["size"], ax=ax, edgecolors="black")
            else:
                nx.draw_networkx_nodes(G, pos, nodelist=nodelist, node_color=self.STYLE_CONFIG[style_key]["color"], node_size=self.STYLE_CONFIG[style_key]["size"], ax=ax, edgecolors="black")

        # ラベル描画
        labels = {n: d.get("label", "") for n, d in G.nodes(data=True)}
        nx.draw_networkx_labels(G, pos, labels=labels, **self.STYLE_CONFIG["font"], ax=ax)
        
        # エッジ描画
        for edge_type in ["default", "potential", "reagent"]:
            edgelist = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == edge_type]
            if not edgelist: continue
            
            style = self.STYLE_CONFIG[f"edge_{edge_type}"]
            connectionstyle = "arc3,rad=0.1"
            if edge_type == "reagent": connectionstyle = "arc3,rad=0.0"
            
            nx.draw_networkx_edges(
                G, pos, edgelist=edgelist,
                edge_color=style["color"],
                width=style["width"],
                style=style["style"],
                alpha=style.get("alpha", 1.0),
                arrowsize=20,
                connectionstyle=connectionstyle,
                ax=ax
            )

        # 凡例
        legend_lines = [
            mlines.Line2D([], [], color='black', lw=2, label='Default Flow (Child->Parent)'),
            mlines.Line2D([], [], color='purple', lw=1, ls='--', label='Potential Sharing (Extra Edges)'),
            mlines.Line2D([], [], color='orange', lw=1, ls=':', label='Reagent Input Candidate'),
        ]
        ax.legend(handles=legend_lines, loc='upper right', fontsize=12)

        plt.title(title, fontsize=18)
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Graph saved to: {output_path}")
        plt.close()

    def _calculate_node_positions(self, G):
        pos = {}
        targets = sorted({d["target"] for n, d in G.nodes(data=True) if d.get("target") is not None})
        current_x_offset = 0.0

        for target_idx in targets:
            sub_nodes = [n for n, d in G.nodes(data=True) if d.get("target") == target_idx]
            if not sub_nodes: continue
            
            levels = sorted({G.nodes[n]["level"] for n in sub_nodes})
            max_width_in_tree = 0
            
            for level in levels:
                nodes_at_level = [n for n in sub_nodes if G.nodes[n].get("level") == level]
                width = (len(nodes_at_level) - 1) * self.LAYOUT_CONFIG["x_gap"]
                start_x = current_x_offset - width / 2.0
                
                for i, node_name in enumerate(nodes_at_level):
                    pos[node_name] = (
                        start_x + i * self.LAYOUT_CONFIG["x_gap"],
                        -level * self.LAYOUT_CONFIG["y_gap"]
                    )
                max_width_in_tree = max(max_width_in_tree, width)
            
            current_x_offset += max_width_in_tree + self.LAYOUT_CONFIG["tree_gap"]
            
        return pos


def visualize_structure():
    print(f"--- Visualizing Problem Structure (Mode: {Config.MODE}) ---")
    
    if Config.MODE in ['auto', 'auto_permutations']:
        targets_config = [t.copy() for t in TARGETS_FOR_AUTO_MODE] 
        apply_auto_factors(targets_config, Config.MAX_MIXER_SIZE)
    elif Config.MODE == 'manual':
        targets_config = TARGETS_FOR_MANUAL_MODE
    else:
        print("Unsupported mode for visualization.")
        return

    tree_structures = build_dfmm_forest(targets_config)
    p_value_maps = calculate_p_values_from_structure(tree_structures, targets_config)
    problem = MTWMProblem(targets_config, tree_structures, p_value_maps)
    
    visualizer = StructureVisualizer(problem, tree_structures)

    # 出力ファイル名の設定（カレントディレクトリに出力）
    basic_out = os.path.join(current_dir, "structure_basic_dfmm.png")
    full_out = os.path.join(current_dir, "structure_full_potential.png")

    print("Generating Basic DFMM Graph...")
    G_basic = visualizer.generate_graph(mode="basic")
    visualizer.draw_and_save(G_basic, basic_out, "Basic DFMM Structure (Mandatory Edges)")
    
    print("Generating Full Potential Graph...")
    G_full = visualizer.generate_graph(mode="full")
    visualizer.draw_and_save(G_full, full_out, "Full Potential Structure (with Sharing Candidates)")
    
    basic_edges = G_basic.number_of_edges()
    full_edges = G_full.number_of_edges()
    print("-" * 50)
    print(f"Visual check completed.")
    print(f"Basic Edges: {basic_edges}")
    print(f"Full Edges : {full_edges}")
    print(f"-> Increase due to sharing: +{full_edges - basic_edges} potential connections")
    print("-" * 50)

if __name__ == "__main__":
    visualize_structure()