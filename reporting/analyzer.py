# reporting/analyzer.py
import os


class PreRunAnalyzer:
    """
    最適化の実行前に、構築された混合ツリーの構造やP値、共有可能性などの
    事前チェックを行い、その結果をレポートファイルとして保存するクラス。
    
    これにより、意図した通りの問題設定になっているかをデバッグしやすくなります。
    このクラスは `base_runner.py` の `_run_single_optimization` から呼び出されます。
    """

    def __init__(self, problem, tree_structures):
        """
        コンストラクタ。

        Args:
            problem (MTWMProblem): 最適化問題の定義オブジェクト (`core/problem.py`)
            tree_structures (list): DFMMによって生成されたツリー構造 (`core/dfmm.py`)
        """
        self.problem = problem
        self.tree_structures = tree_structures

    def generate_report(self, output_dir):
        """
        事前分析レポートを生成し、指定されたディレクトリに保存します。
        ファイル名は `_pre_run_analysis.txt` になります。

        Args:
            output_dir (str): レポートファイルを保存するディレクトリのパス。
        """
        # レポートファイルのパスを構築
        filepath = os.path.join(output_dir, "_pre_run_analysis.txt")
        content = []
        
        # --- 各セクションのコンテンツを構築して結合 ---
        # 1. ツリー構造 (ノードの親子関係)
        content.extend(self._build_tree_structure_section())
        content.append("\n\n" + "=" * 55 + "\n")
        
        # 2. P値 (各ノードの計算されたP値)
        content.extend(self._build_p_values_section())
        content.append("\n\n" + "=" * 55 + "\n")
        
        # 3. 共有可能性 (どのノードがどこに共有できるか)
        content.extend(self._build_sharing_potential_section())

        try:
            # 完成したコンテンツをファイルに書き込み
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(content))
            print(f"Pre-run analysis report saved to: {filepath}")
        except IOError as e:
            # エラーハンドリング
            print(f"Error saving pre-run analysis report: {e}")

    def _build_tree_structure_section(self):
        """セクション1: DFMMによって構築されたツリーの接続情報レポートを構築する。"""
        content = ["--- Section 1: Generated Tree Structures (Node Connections) ---"]
        
        # `tree_structures` (DFMMの生の結果) をループ
        for target_idx, tree in enumerate(self.tree_structures):
            target_info = self.problem.targets_config[target_idx]
            content.append(
                f"\n[Target: {target_info['name']}] (Factors: {target_info['factors']})"
            )
            if not tree:
                content.append("  No nodes generated for this target.")
                continue

            # ノードID (level, node_idx) でソートして、表示順を安定させる
            sorted_nodes = sorted(tree.items())
            
            # 各ノード (親) についてループ
            for node_id, node_data in sorted_nodes:
                level, node_idx = node_id

                # 子ノードのリスト (例: [(2,0), (2,1)]) を文字列に変換
                children_str = ", ".join(
                    [
                        f"mixer_t{target_idx}_l{c[0]}_k{c[1]}"
                        for c in sorted(node_data["children"])
                    ]
                )

                node_name = f"mixer_t{target_idx}_l{level}_k{node_idx}"
                # (例: Node mixer_t0_l1_k0 <-- [mixer_t0_l2_k0, mixer_t0_l2_k1])
                # (例: Node mixer_t0_l2_k0 <-- [Reagents Only])
                content.append(
                    f"  Node {node_name} <-- [{children_str if children_str else 'Reagents Only'}]"
                )
        return content

    def _build_p_values_section(self):
        """セクション2: 計算された各ノードのP値の検証レポートを構築する。"""
        content = ["--- Section 2: Calculated P-values per Node ---"]

        # 1. DFMMノードのP値
        # `problem.p_value_maps` (P値の計算結果) をループ
        for target_idx, p_tree in enumerate(self.problem.p_value_maps):
            target_info = self.problem.targets_config[target_idx]
            content.append(
                f"\n[Target: {target_info['name']}] (Ratios: {target_info['ratios']}, Factors: {target_info['factors']})"
            )
            if not p_tree:
                content.append("  No nodes generated for this target.")
                continue
            
            # ノードIDでソート
            sorted_nodes = sorted(p_tree.items())
            for node_id, p_value in sorted_nodes:
                level, node_idx = node_id
                node_name = f"mixer_t{target_idx}_l{level}_k{node_idx}"
                # (例: Node mixer_t0_l1_k0: P = 6)
                content.append(f"  Node {node_name}: P = {p_value}")

        # 2. ピア(R)ノードのP値
        if self.problem.peer_nodes:
            content.append("\n[Peer Mixing Nodes (1:1 Mix)]")
            for i, peer_node in enumerate(self.problem.peer_nodes):
                # (例: Node peer_mixer_...: P = 6)
                content.append(
                    f"  Node {peer_node['name']}: P = {peer_node['p_value']}"
                )

        return content

    def _build_sharing_potential_section(self):
        """セクション3: 潜在的な共有接続の検証レポートを構築する。
           (P値が一致するかどうかをここで目視確認できる)
        """
        content = [
            "--- Section 3: Potential Sharing Connections (with P-values for validation) ---"
        ]
        
        # `problem.potential_sources_map` (core/problem.py で事前計算されたマップ) を使用
        if not self.problem.potential_sources_map:
            content.append("\nNo potential sharing connections were found.")
            return content

        # 供給先ノードでソートして表示
        sorted_destinations = sorted(self.problem.potential_sources_map.keys())
        
        # 供給先 (dst) ごとにループ
        for dest_node in sorted_destinations:
            sources = self.problem.potential_sources_map[dest_node] # 供給元(src)のリスト
            dst_target_idx, dst_level, dst_node_idx = dest_node

            # 供給先のP値を取得
            p_dst = self.problem.p_value_maps[dst_target_idx].get(
                (dst_level, dst_node_idx), "N/A"
            )
            dest_name = f"mixer_t{dst_target_idx}_l{dst_level}_k{dst_node_idx}"

            if sources:
                # (例: Node mixer_t0_l0_k0 (P=18) can potentially receive from:)
                content.append(
                    f"\nNode {dest_name} (P={p_dst}) can potentially receive from:"
                )
                
                # 供給元 (src) のリストをループ
                for src_target_idx, src_level, src_node_idx in sources:
                    if src_target_idx == "R":
                        # 供給元がピア(R)ノードの場合
                        try:
                            peer_node = self.problem.peer_nodes[src_level]
                            p_src = peer_node["p_value"]
                            src_name = peer_node["name"]
                        except (IndexError, KeyError):
                            p_src = "N/A"
                            src_name = f"Invalid_R_Node_idx{src_level}"
                    else:
                        # 供給元がDFMMノードの場合
                        try:
                            p_src = self.problem.p_value_maps[src_target_idx].get(
                                (src_level, src_node_idx), "N/A"
                            )
                            src_name = (
                                f"mixer_t{src_target_idx}_l{src_level}_k{src_node_idx}"
                            )
                        except (IndexError, TypeError):
                            p_src = "N/A"
                            src_name = f"Invalid_DFMM_Node_{src_target_idx}_{src_level}_{src_node_idx}"
                    
                    # (例:   -> mixer_t1_l1_k0 (P=6))
                    # (ここで P_dst (18) と P_src (6) の関係が妥当か確認できる)
                    content.append(f"  -> {src_name} (P={p_src})")
        return content