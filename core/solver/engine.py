import time
import sys
from collections import defaultdict
from typing import List, Dict, Any, Optional

from ortools.sat.python import cp_model
from utils.config_loader import Config
from utils import (
    create_dfmm_node_name,
    create_intra_key,
    create_inter_key,
    create_peer_key,
    parse_sharing_key,
)
from .solution import OrToolsSolutionModel

sys.setrecursionlimit(2000)

class SolutionPrinter(cp_model.CpSolverSolutionCallback):
    """解が見つかるたびに進捗を表示するコールバック（シンプル版）"""
    def __init__(self):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.__solution_count = 0
        self.__start_time = time.time()

    def on_solution_callback(self):
        self.__solution_count += 1
        current_time = time.time()
        obj = self.ObjectiveValue()
        print(f"Solution #{self.__solution_count}: Objective = {obj}, Time = {current_time - self.__start_time:.2f}s")

    @property
    def solution_count(self):
        return self.__solution_count


class OrToolsSolver:
    """MTWMProblem を Or-Tools CP-SAT モデルに変換し、最適化を実行するクラス。"""

    def __init__(self, problem, objective_mode="waste"):
        self.problem = problem
        self.objective_mode = objective_mode
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        
        self.forest_vars = []
        self.peer_vars = []
        
        self._configure_solver()
        self._set_variables_and_constraints()

    def _configure_solver(self):
        """ソルバーのパラメータ設定"""
        # Config.MAX_CPU_WORKERS が指定されていれば従う、なければ全コア(0)
        if Config.MAX_CPU_WORKERS and Config.MAX_CPU_WORKERS > 0:
            self.solver.parameters.num_workers = Config.MAX_CPU_WORKERS
        else:
            self.solver.parameters.num_workers = 0
        
        if Config.MAX_TIME_PER_RUN_SECONDS and Config.MAX_TIME_PER_RUN_SECONDS > 0:
            self.solver.parameters.max_time_in_seconds = float(Config.MAX_TIME_PER_RUN_SECONDS)

        if Config.ABSOLUTE_GAP_LIMIT is not None:
             self.solver.parameters.absolute_gap_limit = float(Config.ABSOLUTE_GAP_LIMIT)

        # 速度重視設定
        self.solver.parameters.linearization_level = 0
        self.solver.parameters.optimize_with_core = False 
        self.solver.parameters.boolean_encoding_level = 1
        self.solver.parameters.max_num_cuts = 2000 
        self.solver.parameters.cut_level = 2
        self.solver.parameters.log_search_progress = True

        # self.solver.parameters.linearization_level = 2
        # self.solver.parameters.optimize_with_core =False
        # self.solver.parameters.max_num_cuts = 2000 
        # self.solver.parameters.cut_level = 2
        # self.solver.parameters.boolean_encoding_level = 2
        # self.solver.parameters.symmetry_level = 2 
        # self.solver.parameters.log_search_progress = True

    def solve(self):
        start_time = time.time()
        print(f"\n--- Solving (mode: {self.objective_mode.upper()}) with Or-Tools CP-SAT ---")

        solution_printer = SolutionPrinter()
        status = self.solver.Solve(self.model, solution_printer)
        
        elapsed = time.time() - start_time
        best_model = None
        best_value = None
        best_analysis = None

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            best_value = self.solver.ObjectiveValue()
            status_str = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
            print(f"Or-Tools finished: {status_str} solution found. Value: {int(best_value)}")
            print(f"Total solutions found: {solution_printer.solution_count}")
            
            best_model = OrToolsSolutionModel(
                self.problem, self.solver, self.forest_vars, self.peer_vars
            )
            best_analysis = best_model.analyze()
            if isinstance(best_analysis, dict):
                best_analysis["solver_status"] = status_str
        else:
            print(f"Or-Tools Solver status: {self.solver.StatusName(status)}")
            print("--- No solution found (INFEASIBLE or TIMEOUT) ---")
                
        print("--- Or-Tools Solver Finished ---")
        return best_model, best_value, best_analysis, elapsed
    
    def _set_variables_and_constraints(self):
        self._define_or_tools_variables()
        self._set_initial_constraints()
        self._set_conservation_constraints()
        self._set_concentration_constraints()
        self._set_ratio_sum_constraints()
        self._set_leaf_node_constraints()
        self._set_mixer_capacity_constraints()
        self._set_symmetry_breaking_constraints()
        self._set_activity_constraints()
        self._set_peer_mixing_constraints()
        self._set_input_degree_constraints()
        
        # 指定された制約を適用
        self._set_max_reagent_input_per_node_constraint()
        self._set_objective_function()

    def _define_or_tools_variables(self):
        """変数定義：MAX_SHARING_VOLUME を考慮して定義域を設定"""
        for target_idx, z3_tree in enumerate(self.problem.forest):
            tree_data = {}
            for level, z3_nodes in z3_tree.items():
                level_nodes = []
                for node_idx, z3_node in enumerate(z3_nodes):
                    node_name = create_dfmm_node_name(target_idx, level, node_idx)
                    p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
                    f_value = self.problem.targets_config[target_idx]["factors"][level]
                    reagent_max = max(0, f_value - 1)
                    
                    # 共有量の上限を決定
                    # 設定値がある場合は f_value と比較して小さい方を採用
                    # 設定値がない(None)場合は f_value が上限
                    if Config.MAX_SHARING_VOLUME is not None and Config.MAX_SHARING_VOLUME > 0:
                        max_sharing_vol = min(f_value, Config.MAX_SHARING_VOLUME)
                    else:
                        max_sharing_vol = f_value

                    node_vars = {
                        "ratio_vars": [
                            self.model.NewIntVar(0, p_node, f"ratio_{node_name}_r{t}")
                            for t in range(self.problem.num_reagents)
                        ],
                        "reagent_vars": [
                            self.model.NewIntVar(0, reagent_max, f"reagent_vol_{node_name}_r{t}")
                            for t in range(self.problem.num_reagents)
                        ],
                        "intra_sharing_vars": {},
                        "inter_sharing_vars": {},
                        "total_input_var": self.model.NewIntVar(0, f_value, f"TotalInput_{node_name}"),
                        "is_active_var": self.model.NewBoolVar(f"IsActive_{node_name}"),
                        "waste_var": self.model.NewIntVar(0, f_value, f"waste_{node_name}"),
                    }
                    
                    # 内部共有変数の定義（上限適用）
                    for key in z3_node.get("intra_sharing_vars", {}).keys():
                        share_name = f"share_intra_t{target_idx}_l{level}_k{node_idx}_{key}"
                        node_vars["intra_sharing_vars"][key] = self.model.NewIntVar(0, max_sharing_vol, share_name)
                    
                    # 外部共有変数の定義（上限適用）
                    for key in z3_node.get("inter_sharing_vars", {}).keys():
                        share_name = f"share_inter_t{target_idx}_l{level}_k{node_idx}_{key}"
                        node_vars["inter_sharing_vars"][key] = self.model.NewIntVar(0, max_sharing_vol, share_name)
                    
                    level_nodes.append(node_vars)
                tree_data[level] = level_nodes
            self.forest_vars.append(tree_data)
            
        # Peerノードの定義（変更なし）
        for i, z3_peer_node in enumerate(self.problem.peer_nodes):
            name = z3_peer_node["name"]
            p_val = z3_peer_node["p_value"]
            is_generic = z3_peer_node.get("is_generic", False)

            node_vars = {
                "name": name,
                "p_value": p_val,
                "is_generic": is_generic,
                "ratio_vars": [
                    self.model.NewIntVar(0, p_val, f"ratio_{name}_r{t}")
                    for t in range(self.problem.num_reagents)
                ],
                "total_input_var": self.model.NewIntVar(0, 10, f"TotalInput_{name}"),
                "is_active_var": self.model.NewBoolVar(f"IsActive_{name}"),
                "waste_var": self.model.NewIntVar(0, 2, f"waste_{name}"),
                "incoming_bools": {}
            }

            if is_generic:
                candidates = z3_peer_node["candidate_sources"]
                num_candidates = len(candidates)
                idx1 = self.model.NewIntVar(0, num_candidates, f"src_idx1_{name}")
                idx2 = self.model.NewIntVar(0, num_candidates, f"src_idx2_{name}")
                
                node_vars["input_indices"] = [idx1, idx2]
                node_vars["candidate_sources"] = candidates
                node_vars["input_vars"] = {} 

                for c_idx, src_id in enumerate(candidates):
                    is_sel = self.model.NewBoolVar(f"is_sel_{name}_from_{src_id}")
                    b1 = self.model.NewBoolVar(f"b1_{name}_{src_id}")
                    b2 = self.model.NewBoolVar(f"b2_{name}_{src_id}")
                    
                    self.model.Add(idx1 == c_idx).OnlyEnforceIf(b1)
                    self.model.Add(idx1 != c_idx).OnlyEnforceIf(b1.Not())
                    self.model.Add(idx2 == c_idx).OnlyEnforceIf(b2)
                    self.model.Add(idx2 != c_idx).OnlyEnforceIf(b2.Not())
                    
                    self.model.AddBoolOr([b1, b2]).OnlyEnforceIf(is_sel)
                    self.model.AddImplication(b1, is_sel)
                    self.model.AddImplication(b2, is_sel)
                    self.model.AddBoolAnd([b1.Not(), b2.Not()]).OnlyEnforceIf(is_sel.Not())
                    
                    node_vars["incoming_bools"][src_id] = is_sel
                
            else:
                node_vars["source_a_id"] = z3_peer_node["source_a_id"]
                node_vars["source_b_id"] = z3_peer_node["source_b_id"]
                # [一般化] 異重きピアの情報を引き継ぐ（コピー漏れがINFEASIBLE原因だった）
                node_vars["is_hetero"] = z3_peer_node.get("is_hetero", False)
                if node_vars["is_hetero"]:
                    node_vars["weight_a"] = z3_peer_node["weight_a"]
                    node_vars["weight_b"] = z3_peer_node["weight_b"]
                    node_vars["coef_g"] = z3_peer_node["coef_g"]
                    node_vars["ratio_a"] = z3_peer_node.get("ratio_a", 1)
                    node_vars["ratio_b"] = z3_peer_node.get("ratio_b", 1)
                # 体積比 a:b に応じた入力量の上限。異重きは ratio_a/ratio_b、等重きは1。
                _ra = z3_peer_node.get("ratio_a", 1) if node_vars["is_hetero"] else 1
                _rb = z3_peer_node.get("ratio_b", 1) if node_vars["is_hetero"] else 1
                node_vars["input_vars"] = {
                    "from_a": self.model.NewIntVar(0, _ra, f"share_peer_a_to_{name}"),
                    "from_b": self.model.NewIntVar(0, _rb, f"share_peer_b_to_{name}"),
                }
                node_vars["incoming_bools"][node_vars["source_a_id"]] = node_vars["input_vars"]["from_a"]
                node_vars["incoming_bools"][node_vars["source_b_id"]] = node_vars["input_vars"]["from_b"]

            self.peer_vars.append(node_vars)

    # --- ヘルパーメソッド ---
    def _get_input_vars(self, node_vars):
        return (
            node_vars.get("reagent_vars", [])
            + list(node_vars.get("intra_sharing_vars", {}).values())
            + list(node_vars.get("inter_sharing_vars", {}).values())
        )

    def _get_outgoing_vars(self, src_target_idx, src_level, src_node_idx):
        outgoing = []
        key_intra = f"from_{create_intra_key(src_level, src_node_idx)}"
        key_inter = f"from_{create_inter_key(src_target_idx, src_level, src_node_idx)}"
        for dst_target_idx, tree_dst in enumerate(self.forest_vars):
            for dst_level, level_dst in tree_dst.items():
                for dst_node_idx, node_dst in enumerate(level_dst):
                    if src_target_idx == dst_target_idx and key_intra in node_dst.get("intra_sharing_vars", {}):
                        outgoing.append(node_dst["intra_sharing_vars"][key_intra])
                    elif src_target_idx != dst_target_idx and key_inter in node_dst.get("inter_sharing_vars", {}):
                        outgoing.append(node_dst["inter_sharing_vars"][key_inter])
        src_id = (src_target_idx, src_level, src_node_idx)
        for or_peer_node in self.peer_vars:
            if src_id in or_peer_node.get("incoming_bools", {}):
                outgoing.append(or_peer_node["incoming_bools"][src_id])
        return outgoing

    def _get_outgoing_vars_from_peer(self, peer_node_index):
        outgoing = []
        key_inter = f"from_{create_peer_key(peer_node_index)}"
        for dst_target_idx, tree_dst in enumerate(self.forest_vars):
            for dst_level, level_dst in tree_dst.items():
                for dst_node_idx, node_dst in enumerate(level_dst):
                    if key_inter in node_dst.get("inter_sharing_vars", {}):
                        outgoing.append(node_dst["inter_sharing_vars"][key_inter])
        return outgoing

    def _iterate_all_nodes(self):
        for target_idx, tree in enumerate(self.forest_vars):
            for level, nodes in tree.items():
                for node_idx, node in enumerate(nodes):
                    yield target_idx, level, node_idx, node

    # --- 制約メソッド ---
    def _set_initial_constraints(self):
        for target_idx, target in enumerate(self.problem.targets_config):
            if 0 in self.forest_vars[target_idx] and self.forest_vars[target_idx][0]:
                root_vars = self.forest_vars[target_idx][0][0]
                for reagent_idx in range(self.problem.num_reagents):
                    self.model.Add(root_vars["ratio_vars"][reagent_idx] == target["ratios"][reagent_idx])

    def _set_conservation_constraints(self):
        for m_src, l_src, k_src, node_vars in self._iterate_all_nodes():
            total_produced = node_vars["total_input_var"]
            self.model.Add(total_produced == sum(self._get_input_vars(node_vars)))

    def _set_concentration_constraints(self):
        """濃度制約：MAX_SHARING_VOLUME を考慮して変数の積の上限を設定"""
        for dst_target_idx, dst_level, dst_node_idx, node_vars in self._iterate_all_nodes():
            p_dst = self.problem.p_value_maps[dst_target_idx][(dst_level, dst_node_idx)]
            f_dst = self.problem.targets_config[dst_target_idx]["factors"][dst_level]
            
            for reagent_idx in range(self.problem.num_reagents):
                lhs = f_dst * node_vars["ratio_vars"][reagent_idx]
                rhs_terms = []
                rhs_terms.append(p_dst * node_vars["reagent_vars"][reagent_idx])
                
                # --- Intra Sharing ---
                for key, w_var in node_vars.get("intra_sharing_vars", {}).items():
                    key_no_prefix = key.replace("from_", "")
                    parsed = parse_sharing_key(key_no_prefix)
                    l, k = parsed["level"], parsed["node_idx"]
                    
                    r_src = self.forest_vars[dst_target_idx][l][k]["ratio_vars"][reagent_idx]
                    p_src = self.problem.p_value_maps[dst_target_idx][(l, k)]
                    f_src = self.problem.targets_config[dst_target_idx]["factors"][l]
                    
                    # MAX_SHARING_VOLUME を考慮した最大共有量
                    if Config.MAX_SHARING_VOLUME is not None and Config.MAX_SHARING_VOLUME > 0:
                        max_w = min(f_src, Config.MAX_SHARING_VOLUME)
                    else:
                        max_w = f_src
                    
                    prod = self.model.NewIntVar(0, p_src * max_w, f"P_intra_{dst_level}_{dst_node_idx}_r{reagent_idx}_{key}")
                    self.model.AddMultiplicationEquality(prod, [r_src, w_var])
                    rhs_terms.append(prod * (p_dst // p_src))

                # --- Inter Sharing ---
                for key, w_var in node_vars.get("inter_sharing_vars", {}).items():
                    key_no_prefix = key.replace("from_", "")
                    parsed = parse_sharing_key(key_no_prefix)
                    
                    if parsed["type"] == "PEER":
                        peer = self.peer_vars[parsed["idx"]]
                        r_src = peer["ratio_vars"][reagent_idx]
                        p_src = peer["p_value"]
                        # ピア出力を供給先が使う量の上限。他ノードと同様に MAX_SHARING_VOLUME 基準。
                        # （従来は 2 固定だったが、供給量を一律2に縛る根拠がないため統一）
                        if Config.MAX_SHARING_VOLUME is not None and Config.MAX_SHARING_VOLUME > 0:
                            max_w = Config.MAX_SHARING_VOLUME
                        else:
                            max_w = 2
                    else:
                        m, l, k = parsed["target_idx"], parsed["level"], parsed["node_idx"]
                        r_src = self.forest_vars[m][l][k]["ratio_vars"][reagent_idx]
                        p_src = self.problem.p_value_maps[m][(l, k)]
                        f_src = self.problem.targets_config[m]["factors"][l]
                        
                        # MAX_SHARING_VOLUME を考慮した最大共有量
                        if Config.MAX_SHARING_VOLUME is not None and Config.MAX_SHARING_VOLUME > 0:
                            max_w = min(f_src, Config.MAX_SHARING_VOLUME)
                        else:
                            max_w = f_src
                    
                    prod = self.model.NewIntVar(0, p_src * max_w, f"P_inter_{dst_level}_{dst_node_idx}_r{reagent_idx}_{key}")
                    self.model.AddMultiplicationEquality(prod, [r_src, w_var])
                    rhs_terms.append(prod * (p_dst // p_src))

                self.model.Add(lhs == sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
            is_active = node_vars["is_active_var"]
            self.model.Add(sum(node_vars["ratio_vars"]) == p_node).OnlyEnforceIf(is_active)
            for r_var in node_vars["ratio_vars"]:
                self.model.Add(r_var == 0).OnlyEnforceIf(is_active.Not())

    def _set_leaf_node_constraints(self):
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
            f_node = self.problem.targets_config[target_idx]["factors"][level]
            if p_node == f_node:
                for t in range(self.problem.num_reagents):
                    self.model.Add(node_vars["ratio_vars"][t] == node_vars["reagent_vars"][t])

    def _set_mixer_capacity_constraints(self):
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            f_value = self.problem.targets_config[target_idx]["factors"][level]
            total_sum = node_vars["total_input_var"]
            is_active = node_vars["is_active_var"]
            if level == 0:
                self.model.Add(total_sum == f_value)
                self.model.Add(is_active == 1)
            else:
                self.model.Add(total_sum == f_value).OnlyEnforceIf(is_active)
                self.model.Add(total_sum == 0).OnlyEnforceIf(is_active.Not())

    def _set_activity_constraints(self):
        for (src_target_idx, src_level, src_node_idx, node_vars) in self._iterate_all_nodes():
            if src_level == 0: continue
            total_used = sum(self._get_outgoing_vars(src_target_idx, src_level, src_node_idx))
            is_active = node_vars["is_active_var"]
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_active)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_active.Not())
        for i, or_peer_node in enumerate(self.peer_vars):
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            is_active = or_peer_node["is_active_var"]
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_active)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_active.Not())

    def _set_peer_mixing_constraints(self):
        for i, or_peer_node in enumerate(self.peer_vars):
            if or_peer_node.get("is_generic"):
                self._set_dynamic_peer_constraints(or_peer_node)
            else:
                self._set_fixed_peer_constraints(or_peer_node)

    def _set_dynamic_peer_constraints(self, or_peer_node):
        is_active = or_peer_node["is_active_var"]
        idx1, idx2 = or_peer_node["input_indices"]
        candidates = or_peer_node["candidate_sources"]
        num_candidates = len(candidates)
        DUMMY_IDX = num_candidates 
        self.model.Add(idx1 < num_candidates).OnlyEnforceIf(is_active)
        self.model.Add(idx2 < num_candidates).OnlyEnforceIf(is_active)
        self.model.Add(idx1 < idx2).OnlyEnforceIf(is_active)
        self.model.Add(idx1 == DUMMY_IDX).OnlyEnforceIf(is_active.Not())
        self.model.Add(idx2 == DUMMY_IDX).OnlyEnforceIf(is_active.Not())
        self.model.Add(or_peer_node["total_input_var"] == 2).OnlyEnforceIf(is_active)
        self.model.Add(or_peer_node["total_input_var"] == 0).OnlyEnforceIf(is_active.Not())
        for reagent_idx in range(self.problem.num_reagents):
            candidate_ratio_vars = []
            for (m, l, k) in candidates:
                src_var = self.forest_vars[m][l][k]["ratio_vars"][reagent_idx]
                candidate_ratio_vars.append(src_var)
            candidate_ratio_vars.append(self.model.NewConstant(0))
            val1 = self.model.NewIntVar(0, or_peer_node["p_value"], f"val1_{or_peer_node['name']}_r{reagent_idx}")
            self.model.AddElement(idx1, candidate_ratio_vars, val1)
            val2 = self.model.NewIntVar(0, or_peer_node["p_value"], f"val2_{or_peer_node['name']}_r{reagent_idx}")
            self.model.AddElement(idx2, candidate_ratio_vars, val2)
            self.model.Add(2 * or_peer_node["ratio_vars"][reagent_idx] == val1 + val2)
        self.model.Add(sum(or_peer_node["ratio_vars"]) == or_peer_node["p_value"]).OnlyEnforceIf(is_active)
        self.model.Add(sum(or_peer_node["ratio_vars"]) == 0).OnlyEnforceIf(is_active.Not())

    def _set_fixed_peer_constraints(self, or_peer_node):
        total_input = or_peer_node["total_input_var"]
        is_active = or_peer_node["is_active_var"]
        w_a = or_peer_node["input_vars"]["from_a"]
        w_b = or_peer_node["input_vars"]["from_b"]
        # 体積比 a:b に応じた入力消費量。異重きは a:b、等重きは 1:1。
        if or_peer_node.get("is_hetero", False):
            in_a = or_peer_node.get("ratio_a", 1)
            in_b = or_peer_node.get("ratio_b", 1)
        else:
            in_a, in_b = 1, 1
        self.model.Add(total_input == w_a + w_b)
        self.model.Add(w_a == in_a).OnlyEnforceIf(is_active)
        self.model.Add(w_b == in_b).OnlyEnforceIf(is_active)
        self.model.Add(total_input == 0).OnlyEnforceIf(is_active.Not())
        self.model.Add(w_a == 0).OnlyEnforceIf(is_active.Not())
        self.model.Add(w_b == 0).OnlyEnforceIf(is_active.Not())
        p_val = or_peer_node["p_value"]
        r_new_vars = or_peer_node["ratio_vars"]
        self.model.Add(sum(r_new_vars) == p_val).OnlyEnforceIf(is_active)
        self.model.Add(sum(r_new_vars) == 0).OnlyEnforceIf(is_active.Not())
        m_a, l_a, k_a = or_peer_node["source_a_id"]
        r_a_vars = self.forest_vars[m_a][l_a][k_a]["ratio_vars"]
        m_b, l_b, k_b = or_peer_node["source_b_id"]
        r_b_vars = self.forest_vars[m_b][l_b][k_b]["ratio_vars"]

        if or_peer_node.get("is_hetero", False):
            # [一般化] 異重きピア: 体積比 a:b の濃度混合。
            # g * r_new[k] == ca * r_a[k] + cb * r_b[k]
            # ca = a*L/weight_a, cb = b*L/weight_b, L = lcm(weight_a, weight_b)
            # g = (a+b)*L / p_new （problem側で計算済み coef_g）
            from math import lcm
            wa = or_peer_node["weight_a"]
            wb = or_peer_node["weight_b"]
            ra = or_peer_node.get("ratio_a", 1)
            rb = or_peer_node.get("ratio_b", 1)
            L = lcm(wa, wb)
            ca = ra * (L // wa)
            cb = rb * (L // wb)
            g = or_peer_node["coef_g"]
            for t in range(self.problem.num_reagents):
                self.model.Add(
                    g * r_new_vars[t] == ca * r_a_vars[t] + cb * r_b_vars[t]
                ).OnlyEnforceIf(is_active)
        else:
            # 等重きピア(従来): 1:1 混合
            for t in range(self.problem.num_reagents):
                self.model.Add(2 * r_new_vars[t] == r_a_vars[t] + r_b_vars[t]).OnlyEnforceIf(is_active)

    def _set_input_degree_constraints(self):
        max_fan_in = getattr(Config, "MAX_SHARED_INPUTS", None)
        if max_fan_in is None: return
        print(f"--- Setting max shared input types (Fan-in) per node to {max_fan_in} ---")
        for _, _, _, node_vars in self._iterate_all_nodes():
            sharing_vars = []
            sharing_vars.extend(node_vars.get("intra_sharing_vars", {}).values())
            sharing_vars.extend(node_vars.get("inter_sharing_vars", {}).values())
            if not sharing_vars: continue
            is_used_bools = []
            for var in sharing_vars:
                is_used = self.model.NewBoolVar(f"is_used_{var.Name()}")
                self.model.Add(var > 0).OnlyEnforceIf(is_used)
                self.model.Add(var == 0).OnlyEnforceIf(is_used.Not())
                is_used_bools.append(is_used)
            self.model.Add(sum(is_used_bools) <= max_fan_in)
        if max_fan_in < 2:
            for peer in self.peer_vars:
                if peer.get("is_generic"):
                    self.model.Add(peer["is_active_var"] == 0)

    def _set_symmetry_breaking_constraints(self):
        for m, tree_vars in enumerate(self.forest_vars):
            for l, nodes_vars_list in tree_vars.items():
                if len(nodes_vars_list) > 1:
                    for k in range(len(nodes_vars_list) - 1):
                        node_k = nodes_vars_list[k]
                        node_k1 = nodes_vars_list[k+1]
                        self.model.Add(node_k["is_active_var"] >= node_k1["is_active_var"])
                        self.model.Add(node_k["total_input_var"] >= node_k1["total_input_var"])
        peers_by_p = defaultdict(list)
        for p_var in self.peer_vars:
            if p_var.get("is_generic"):
                peers_by_p[p_var["p_value"]].append(p_var)
        for p_val, peers in peers_by_p.items():
            if len(peers) > 1:
                for i in range(len(peers) - 1):
                    peer_k = peers[i]
                    peer_k1 = peers[i+1]
                    self.model.Add(peer_k["is_active_var"] >= peer_k1["is_active_var"])
                    idx1_k = peer_k["input_indices"][0]
                    idx1_k1 = peer_k1["input_indices"][0]
                    self.model.Add(idx1_k <= idx1_k1).OnlyEnforceIf(peer_k1["is_active_var"])

    def _set_max_reagent_input_per_node_constraint(self):
        """
        各ノードへの「個別の試薬エッジの重み」を制限するハード制約。
        例: limit=2 の場合、試薬Aの投入量 <= 2, 試薬Bの投入量 <= 2 ... となる。
        （合計値の制限ではない）
        """
        max_limit = Config.MAX_TOTAL_REAGENT_INPUT_PER_NODE
        
        # 設定値がNoneまたは負の値の場合は適用しない（0はあり得るので許容する場合は注意）
        if max_limit is None or max_limit < 0:
            return

        print(f"--- Setting max reagent input PER EDGE (HARD Constraint) to {max_limit} ---")
        
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            reagent_vars = node_vars.get("reagent_vars", [])
            
            # 各試薬変数を個別にチェック
            for r_var in reagent_vars:
                # 変数 <= max_limit (個別の制限)
                self.model.Add(r_var <= max_limit)

    def _set_objective_function(self):
        """目的関数の設定（純粋な最小化）"""
        all_waste_vars = []
        all_activity_vars = []
        all_reagent_vars = []

        for (src_target_idx, src_level, src_node_idx, node_vars) in self._iterate_all_nodes():
            if src_level != 0:
                total_prod = node_vars["total_input_var"]
                total_used = sum(self._get_outgoing_vars(src_target_idx, src_level, src_node_idx))
                waste_var = node_vars["waste_var"]
                self.model.Add(waste_var == total_prod - total_used)
                all_waste_vars.append(waste_var)
            all_activity_vars.append(node_vars["is_active_var"])
            all_reagent_vars.extend(node_vars.get("reagent_vars", []))

        for i, or_peer_node in enumerate(self.peer_vars):
            total_prod = or_peer_node["total_input_var"]
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            waste_var = or_peer_node["waste_var"]
            self.model.Add(waste_var == total_prod - total_used)
            all_waste_vars.append(waste_var)
            all_activity_vars.append(or_peer_node["is_active_var"])

        total_waste = sum(all_waste_vars)
        if self.objective_mode == "waste":
            self.model.Add(total_waste >= 0)
        
        total_operations = sum(all_activity_vars)
        total_reagents = sum(all_reagent_vars)

        if self.objective_mode == "waste":
            self.model.Minimize(total_waste)
            return total_waste
        elif self.objective_mode == "operations":
            self.model.Minimize(total_operations)
            return total_operations
        elif self.objective_mode == "reagents":
            self.model.Minimize(total_reagents)
            return total_reagents
        else:
            raise ValueError(f"Unknown optimization mode: '{self.objective_mode}'")