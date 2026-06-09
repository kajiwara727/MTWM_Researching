import os
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.model.problem import MTWMProblem
from core.solver.engine import OrToolsSolver
from reporting.analyzer import PreRunAnalyzer
from reporting.reporter import SolutionReporter
from utils.config_loader import Config

class ExecutionEngine:
    """
    単一のターゲット設定に対する最適化プロセス（構築→計算→レポート）
    を実行・管理するクラス。
    """

    def __init__(self, config):
        self.config = config

    def run_single_optimization(self, targets_config_for_run, output_dir, run_name_for_report):
        """
        最適化ワークフローを実行します。

        Returns:
            tuple: (final_value, elapsed_time, ops, reagents, total_waste)
        """
        # --- 実行設定をコンソールに出力 ---
        print("\n--- Configuration for this run ---")
        print(f"Run Name: {run_name_for_report}")
        for target in targets_config_for_run:
            print(f"  - {target['name']}: Ratios = {target['ratios']}, Factors = {target['factors']}")
        print(f"Optimization Mode: {self.config.OPTIMIZATION_MODE.upper()}")
        print("-" * 35 + "\n")

        # 1. DFMMアルゴリズムでツリー構造とP値を計算
        tree_structures = build_dfmm_forest(targets_config_for_run)
        p_value_maps = calculate_p_values_from_structure(tree_structures, targets_config_for_run)

        # 2. 最適化問題オブジェクトを生成
        problem = MTWMProblem(targets_config_for_run, tree_structures, p_value_maps)

        # 3. 出力ディレクトリ作成と事前分析
        os.makedirs(output_dir, exist_ok=True)
        print(f"All outputs for this run will be saved to: '{output_dir}/'")
        
        analyzer = PreRunAnalyzer(problem, tree_structures)
        analyzer.generate_report(output_dir)

        # 4. ソルバー初期化と実行
        solver = OrToolsSolver(problem, objective_mode=self.config.OPTIMIZATION_MODE)
        best_model, final_value, best_analysis, elapsed_time = solver.solve()

        # 5. レポート生成
        report_settings = {
            "max_sharing_volume": self.config.MAX_SHARING_VOLUME or "No limit",
            "max_total_reagent_input_per_node": self.config.MAX_TOTAL_REAGENT_INPUT_PER_NODE or "No limit",
            "max_level_diff": self.config.MAX_LEVEL_DIFF or "No limit",
            "max_mixer_size": self.config.MAX_MIXER_SIZE,
        }
        
        reporter = SolutionReporter(
            problem,
            best_model,
            objective_mode=self.config.OPTIMIZATION_MODE,
            enable_visualization=self.config.ENABLE_VISUALIZATION,
            optimization_settings=report_settings,
        )

        ops = None
        reagents = None
        total_waste = None

        if best_model:
            reporter.generate_full_report(final_value, elapsed_time, output_dir)
            ops = best_analysis.get("total_operations")
            reagents = best_analysis.get("total_reagent_units")
            total_waste = best_analysis.get("total_waste")
        else:
            print("\n--- No solution found for this configuration ---")

        return final_value, elapsed_time, ops, reagents, total_waste