from utils import (
    create_dfmm_node_name,
    create_intra_key,
    create_inter_key,
    create_peer_key,
    parse_sharing_key,
)

class OrToolsSolutionModel:
    """
    Or-Toolsソルバーが見つけた「解」を保持し、分析データを提供するクラス。
    """
    def __init__(self, problem, solver, forest_vars, peer_vars):
        self.problem = problem
        self.solver = solver
        self.forest_vars = forest_vars
        self.peer_vars = peer_vars
        self.num_reagents = problem.num_reagents

    def _v(self, or_tools_var):
        val = self.solver.Value(or_tools_var)
        return int(val) if val is not None else 0

    def analyze(self):
        """解を分析し、レポート用の辞書を返します。"""
        results = {
            "total_operations": 0,
            "total_reagent_units": 0,
            "total_waste": 0,
            "reagent_usage": {},
            "nodes_details": [],
        }

        # 1. DFMMノードの分析
        for target_idx, tree in enumerate(self.forest_vars):
            for level, nodes in tree.items():
                for node_idx, node_vars in enumerate(nodes):
                    total_input = self._v(node_vars["total_input_var"])
                    if total_input == 0:
                        continue

                    results["total_operations"] += 1
                    
                    reagent_vals = [self._v(r) for r in node_vars["reagent_vars"]]
                    for r_idx, val in enumerate(reagent_vals):
                        if val > 0:
                            results["total_reagent_units"] += val
                            results["reagent_usage"][r_idx] = (
                                results["reagent_usage"].get(r_idx, 0) + val
                            )
                    
                    if level != 0:
                        results["total_waste"] += self._v(node_vars["waste_var"])
                    
                    node_name = create_dfmm_node_name(target_idx, level, node_idx)
                    results["nodes_details"].append(
                        {
                            "target_id": target_idx,
                            "level": level,
                            "name": node_name,
                            "total_input": total_input,
                            "ratio_composition": [self._v(r) for r in node_vars["ratio_vars"]],
                            "mixing_str": self._generate_mixing_description(node_vars, target_idx),
                        }
                    )

        # 2. ピア(R)ノードの分析 [Modified]
        for i, peer_node_vars in enumerate(self.peer_vars):
            total_input = self._v(peer_node_vars["total_input_var"])
            if total_input == 0:
                continue

            results["total_operations"] += 1
            results["total_waste"] += self._v(peer_node_vars["waste_var"])

            # 混合内容の文字列生成 (Dynamic対応)
            if peer_node_vars.get("is_generic"):
                # [Dynamic] 選択された変数を探す
                selected_names = []
                for src_id, var in peer_node_vars["input_vars"].items():
                    if self._v(var) > 0:
                        name = create_dfmm_node_name(*src_id)
                        selected_names.append(f"1 x {name}")
                
                mixing_str = " + ".join(selected_names)
                # 便宜上のレベル（P値から推測するか、単に0.5とする）
                avg_level = 0.5 
            else:
                # [Fixed]
                z3_peer_node = self.problem.peer_nodes[i]
                m_a, l_a, k_a = z3_peer_node["source_a_id"]
                name_a = create_dfmm_node_name(m_a, l_a, k_a)
                m_b, l_b, k_b = z3_peer_node["source_b_id"]
                name_b = create_dfmm_node_name(m_b, l_b, k_b)
                
                mixing_str = f"1 x {name_a} + 1 x {name_b}"
                avg_level = (l_a + l_b) / 2.0 - 0.5
            
            results["nodes_details"].append(
                {
                    "target_id": -1,
                    "level": avg_level,
                    "name": peer_node_vars["name"],
                    "total_input": total_input,
                    "ratio_composition": [self._v(r) for r in peer_node_vars["ratio_vars"]],
                    "mixing_str": mixing_str,
                }
            )

        results["nodes_details"].sort(key=lambda x: (x["target_id"], x["level"]))
        return results

    def _generate_mixing_description(self, node_vars, target_idx):
        desc = []
        for r_idx, r_var in enumerate(node_vars.get("reagent_vars", [])):
            if (val := self._v(r_var)) > 0:
                desc.append(f"{val} x Reagent{r_idx+1}")
                
        for key, w_var in node_vars.get("intra_sharing_vars", {}).items():
            if (val := self._v(w_var)) > 0:
                key_no_prefix = key.replace("from_", "")
                parsed = parse_sharing_key(key_no_prefix)
                node_name = create_dfmm_node_name(target_idx, parsed["level"], parsed["node_idx"])
                desc.append(f"{val} x {node_name}")
                
        for key, w_var in node_vars.get("inter_sharing_vars", {}).items():
            if (val := self._v(w_var)) > 0:
                key_no_prefix = key.replace("from_", "")
                parsed = parse_sharing_key(key_no_prefix)
                if parsed["type"] == "PEER":
                    peer_node_name = self.problem.peer_nodes[parsed["idx"]]["name"]
                    desc.append(f"{val} x {peer_node_name}")
                elif parsed["type"] == "DFMM":
                    node_name = create_dfmm_node_name(parsed["target_idx"], parsed["level"], parsed["node_idx"])
                    desc.append(f"{val} x {node_name}")
        return " + ".join(desc)