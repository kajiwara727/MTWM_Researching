import os
import sys
from collections import defaultdict

# --- パス解決 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)
# --------------------

# 必要なモジュールをインポート
from utils.config_loader import Config
from utils import create_dfmm_node_name
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.model.problem import MTWMProblem
from scenarios import TARGETS_FOR_MANUAL_MODE, TARGETS_FOR_AUTO_MODE
from core.algorithm.dfmm import apply_auto_factors

def count_edges_for_analysis():
    """
    現在の設定に基づいてMTWMProblemを構築し、
    ソルバーに渡される「エッジ（接続候補）」の数と詳細をテキストファイルに出力します。
    """
    
    output_filepath = os.path.join(current_dir, "edge_analysis_result.txt")

    with open(output_filepath, "w", encoding="utf-8") as f:
        
        def log(message=""):
            print(message)
            f.write(message + "\n")

        # 1. ターゲット設定の取得
        log(f"--- Edge Analysis for Mode: {Config.MODE} ---")
        if Config.MODE in ['auto', 'auto_permutations']:
            targets_config = [t.copy() for t in TARGETS_FOR_AUTO_MODE] 
            apply_auto_factors(targets_config, Config.MAX_MIXER_SIZE)
        elif Config.MODE == 'manual':
            targets_config = TARGETS_FOR_MANUAL_MODE
        else:
            log(f"Mode '{Config.MODE}' is not supported.")
            return

        log(f"Run Name: {Config.RUN_NAME}")
        for t in targets_config:
            log(f"  Target: {t['name']}")
            log(f"    - Ratios:  {t['ratios']}")
            log(f"    - Factors: {t['factors']}")
        
        # 接続モードの表示 (Configに属性がない場合を考慮してgetattr)
        peer_mode = getattr(Config, "PEER_CONNECTION_MODE", "fixed")
        log(f"  Peer Connection Mode: {peer_mode}")
        log("-" * 60)

        # 2. 問題構造の構築
        tree_structures = build_dfmm_forest(targets_config)
        p_value_maps = calculate_p_values_from_structure(tree_structures, targets_config)
        problem = MTWMProblem(targets_config, tree_structures, p_value_maps)

        # --- 集計用変数の初期化 ---
        num_reagents = len(targets_config[0]['ratios'])
        total_dfmm_nodes = sum(len(nodes) for tree in problem.forest for nodes in tree.values())
        total_reagent_edges = total_dfmm_nodes * num_reagents
        
        counts = defaultdict(int)
        
        # デフォルト接続の特定用セット
        default_connections = set()
        for t_idx, tree in enumerate(tree_structures):
            for (p_lvl, p_idx), data in tree.items():
                for (c_lvl, c_idx) in data['children']:
                    dst = (t_idx, p_lvl, p_idx)
                    src = (t_idx, c_lvl, c_idx)
                    default_connections.add((dst, src))

        # --- エッジカウント処理 ---
        # (1) DFMMノードへの入力
        for dst_key, sources in problem.potential_sources_map.items():
            dst_target, _, _ = dst_key
            for src in sources:
                src_target, _, _ = src
                connection_pair = (dst_key, src)
                
                if src_target == "R":
                    counts["Peer-Sharing (Peer->Node)"] += 1
                elif src_target != dst_target:
                    counts["Inter-Sharing (Cross Tree)"] += 1
                else:
                    if connection_pair in default_connections:
                        counts["Default DFMM (Child->Parent)"] += 1
                    else:
                        counts["Intra-Sharing (Skip Level)"] += 1

        # (2) Peerノードへの入力 [Modified]
        # is_generic フラグによってカウント方法を変える
        for peer in problem.peer_nodes:
            if peer.get("is_generic", False):
                # Dynamic: 候補の数だけエッジがある
                counts["Node->Peer (Candidates)"] += len(peer["candidate_sources"])
            else:
                # Fixed: 必ず2本
                counts["Node->Peer (Fixed Inputs)"] += 2

        total_mixing_edges = sum(counts.values())

        # --- 3. 分析サマリー出力 ---
        log("\n" + "="*30 + " EDGE COUNT SUMMARY " + "="*30)
        log(f"Total Nodes (DFMM): {total_dfmm_nodes}")
        log(f"Total Peer Nodes:   {len(problem.peer_nodes)}")
        log("-" * 80)
        
        log(f"[1] Reagent Edges (Variables): {total_reagent_edges}")
        log(f"[2] Mixing Node Edges (Total): {total_mixing_edges}")
        log(f"    --- Breakdown ---")
        
        display_keys = [
            "Default DFMM (Child->Parent)", 
            "Intra-Sharing (Skip Level)", 
            "Inter-Sharing (Cross Tree)", 
            "Peer-Sharing (Peer->Node)", 
            "Node->Peer (Fixed Inputs)",
            "Node->Peer (Candidates)" # 追加
        ]
        
        for key in display_keys:
            if counts[key] > 0 or key == "Node->Peer (Fixed Inputs)": # 0でも一応表示しておくと分かりやすい場合も
                log(f"    {key:<35}: {counts[key]:>5}")
        
        log("=" * 80)

        # --- 4. 接続詳細リストの出力 (New) ---
        log("\n" + "="*30 + " [3] CONNECTION DETAILS " + "="*30)
        log("(Format: Destination <--- Source [Type])")
        
        # A. Peerノードへの入力 [Modified]
        if problem.peer_nodes:
            log("\n--- A. Node -> Peer (Fixed Inputs / Candidates) ---")
            for peer in problem.peer_nodes:
                p_name = peer["name"]
                
                if peer.get("is_generic", False):
                    # Dynamic Peer
                    for src in peer["candidate_sources"]:
                        src_name = create_dfmm_node_name(*src)
                        log(f"{p_name:<30} <--- {src_name} [Candidate]")
                else:
                    # Fixed Peer (Legacy)
                    src_a = create_dfmm_node_name(*peer["source_a_id"])
                    src_b = create_dfmm_node_name(*peer["source_b_id"])
                    log(f"{p_name:<30} <--- {src_a} [Fixed A]")
                    log(f"{p_name:<30} <--- {src_b} [Fixed B]")
        
        # B. DFMMノードへの入力 (Potential)
        log("\n--- B. Inputs to DFMM Nodes (Default & Potential) ---")
        
        sorted_destinations = sorted(problem.potential_sources_map.keys())
        current_target = -1
        
        for dst_key in sorted_destinations:
            dst_target, dst_level, dst_node = dst_key
            
            if dst_target != current_target:
                t_name = targets_config[dst_target]['name']
                log(f"\n[Target {dst_target+1}: {t_name}]")
                current_target = dst_target

            dst_name = create_dfmm_node_name(dst_target, dst_level, dst_node)
            sources = problem.potential_sources_map[dst_key]
            
            for src in sources:
                src_target, src_level, src_node = src
                
                if src_target == "R":
                    src_name = problem.peer_nodes[src_level]["name"]
                    edge_type = "Peer-Sharing"
                else:
                    src_name = create_dfmm_node_name(src_target, src_level, src_node)
                    if src_target != dst_target:
                        edge_type = "Inter-Sharing"
                    elif (dst_key, src) in default_connections:
                        edge_type = "Default DFMM"
                    else:
                        edge_type = "Intra-Sharing"
                
                log(f"  {dst_name:<30} <--- {src_name:<30} [{edge_type}]")

    print(f"\nAnalysis results saved to: {output_filepath}")

if __name__ == "__main__":
    count_edges_for_analysis()