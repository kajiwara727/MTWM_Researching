import os
from .visualizer import SolutionVisualizer

class SolutionReporter:
    """
    ソルバーが見つけた解（OrToolsSolutionModel）を解析し、
    人間が読める形式のテキストベースのレポート (summary.txt) を生成し、
    可視化モジュール (visualizer.py) を呼び出すクラス。
    
    `base_runner.py` の `_run_single_optimization` から呼び出されます。
    """

    def __init__(
        self,
        problem,
        model,
        objective_mode="waste",
        enable_visualization=True,
        optimization_settings=None, 
    ):
        """
        コンストラクタ。

        Args:
            problem (MTWMProblem): 最適化問題の定義オブジェクト。
            model (OrToolsSolutionModel or similar): ソルバーの解をラップしたオブジェクト。(解が見つからなかった場合は None)
            objective_mode (str): 最適化の目的 ('waste', 'operations', 'reagents')。
            enable_visualization (bool): 可視化 (PNG生成) を行うかどうか。
        """
        self.problem = problem
        self.model = model 
        self.objective_mode = objective_mode
        self.enable_visualization = enable_visualization

        # デフォルト値を定義
        default_settings = {
            "max_sharing_volume": "No limit",
            "max_level_diff": "No limit",
            "max_mixer_size": "N/A",
        }

        # 受け取った設定で上書き
        if optimization_settings:
            default_settings.update(optimization_settings)
        self.optimization_settings = default_settings

    def generate_full_report(self, min_value, elapsed_time, output_dir):
        """
        解の分析、コンソールへのサマリー出力、ファイルへの詳細レポート保存、
        そして結果の可視化という一連のレポート生成プロセスを実行します。
        
        Args:
            min_value (float): ソルバーが見つけた目的変数の最小値 (例: 2.0)
            elapsed_time (float): 計算にかかった時間 (秒)
            output_dir (str): レポートを保存するディレクトリ
        """
        
        # 1. 解の分析
        # OrToolsSolutionModel の analyze() メソッドを呼び出し、
        # 解の詳細 (操作回数, 廃棄物量, 混合手順など) を辞書として取得
        analysis_results = self.model.analyze()

        # (目的が 'waste' の場合、min_value がそのまま総廃棄物量になる)
        if self.objective_mode == "waste" and analysis_results is not None:
            analysis_results["total_waste"] = int(min_value)

        # 2. コンソールへのサマリー出力
        self._print_console_summary(analysis_results, min_value, elapsed_time)

        # 3. ファイル (summary.txt) への詳細レポート保存
        self._save_summary_to_file(
            analysis_results, min_value, elapsed_time, output_dir
        )
        
        # 4. 可視化 (PNG生成)
        if self.model and self.enable_visualization: 
            # 可視化が有効で、解が存在する場合
            visualizer = SolutionVisualizer(self.problem, self.model)
            visualizer.visualize_solution(output_dir)
        elif self.model:
            print("Skipping graph visualization (disabled by config).") 

    def _print_console_summary(self, results, min_value, elapsed_time):
        """ヘルパー: コンソールに最適化結果の概要を出力する"""
        time_str = f"(in {elapsed_time:.2f} sec)"
        print(f"\n<Improvement>Optimal Solution Found {time_str}")
        
        if self.objective_mode == "waste":
            objective_str = "Minimum Total Waste"
        elif self.objective_mode == "operations":
            objective_str = "Minimum Operations"
        else:
            objective_str = "Minimum Total Reagents"
            
        print(f"{objective_str}: {min_value}")
        print("=" * 18 + " SUMMARY " + "=" * 18)
        if results:
            print(f"Total mixing operations: {results['total_operations']}")
            print(f"Total waste generated: {results['total_waste']}")
            print(f"Total reagent units used: {results['total_reagent_units']}")
            print("\nReagent usage breakdown:")
            for r_idx in sorted(results["reagent_usage"].keys()):
                print(f"  Reagent {r_idx+1}: {results['reagent_usage'][r_idx]} unit(s)")
        print("=" * 45)

    def _save_summary_to_file(self, results, min_value, elapsed_time, output_dir):
        """ヘルパー: summary.txt ファイルに詳細レポートを書き込む"""
        filepath = os.path.join(output_dir, "summary.txt")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                # レポートの全内容を文字列リストとして構築
                content = self._build_summary_file_content(
                    results, min_value, elapsed_time, output_dir
                )
                # ファイルに書き込み
                f.write("\n".join(content))
            print(f"\nResults summary saved to: {filepath}")
        except IOError as e:
            print(f"\nError saving results to file: {e}")

    def _build_summary_file_content(self, results, min_value, elapsed_time, dir_name):
        """ヘルパー: summary.txt に書き込む内容（文字列リスト）を構築する"""
        
        # --- ヘッダー ---
        if self.objective_mode == "waste":
            objective_str = "Minimum Total Waste"
        elif self.objective_mode == "operations":
            objective_str = "Minimum Operations"
        else:
            objective_str = "Minimum Total Reagents"
        content = [
            "=" * 40,
            f"Optimization Results for: {os.path.basename(dir_name)}",
            "=" * 40,
            f"\nSolved in {elapsed_time:.2f} seconds.",
            "\n--- Target Configuration ---",
        ]
        
        # --- ターゲット設定 ---
        for i, target in enumerate(self.problem.targets_config):
            content.extend(
                [
                    f"Target {i+1}:",
                    f"  Ratios: {' : '.join(map(str, target['ratios']))}",
                    f"  Factors: {target['factors']}",
                ]
            )
            
        settings = self.optimization_settings

        # --- 最適化設定 (config.py の内容) ---
        content.extend(
            [
                "\n--- Optimization Settings ---",
                f"Optimization Mode: {self.objective_mode.upper()}",
                f"Max Sharing Volume: {settings['max_sharing_volume']}",
                f"Max Level Difference: {settings['max_level_diff']}",
                f"Max Mixer Size: {settings['max_mixer_size']}",
                "-" * 28,
                f"\n{objective_str}: {min_value}", # 目的変数の最小値
            ]
        )

        # --- 全体サマリー (analyze() の結果) ---
        if results:
            content.extend(
                [
                    f"Total mixing operations: {results['total_operations']}",
                    f"Max Total Reagent Input per Node: {settings['max_total_reagent_input_per_node']}",
                    f"Total waste generated: {results['total_waste']}",
                    f"Total reagent units used: {results['total_reagent_units']}",
                    "\n--- Reagent Usage Breakdown ---",
                ]
            )
            # 試薬ごとの使用量
            for t in sorted(results["reagent_usage"].keys()):
                content.append(
                    f"  Reagent {t+1}: {results['reagent_usage'][t]} unit(s)"
                )
            content.append("\n\n--- Mixing Process Details ---") # 混合プロセスの詳細

            # --- 混合プロセス詳細 ---
            # (analyze() の "nodes_details" リストをループ)
            current_target = -2 # ターゲットIDの区切りを検出するための変数

            for detail in results["nodes_details"]:
                # ターゲットIDが変わったら、ヘッダー (例: [Target 1 (Product_A)]) を出力
                if detail["target_id"] != current_target:
                    current_target = detail["target_id"]
                    if current_target == -1:
                        content.append("\n[Peer Mixing Nodes (1:1 Mix)]")
                    else:
                        content.append(
                            f"\n[Target {current_target + 1} ({self.problem.targets_config[current_target]['name']})]"
                        )

                # レベル (ピア(R)ノードは 0.5 など小数)
                level_str = (
                    f"{detail['level']}"
                    if isinstance(detail['level'], int)
                    else f"{detail['level']:.1f}"
                )

                # (例:   Node mixer_t0_l1_k0: total_input = 6)
                # (例:     Ratio composition: [1, 5, 0])
                # (例:     Mixing: 1 x Reagent1 + 5 x Reagent2)
                content.extend(
                    [
                        f" Level {level_str}:",
                        f"   Node {detail['name']}: total_input = {detail['total_input']}",
                        f"     Ratio composition: {detail['ratio_composition']}",
                        f"     Mixing: {detail['mixing_str']}"
                        if detail["mixing_str"]
                        else "     (No mixing actions for this node)",
                    ]
                )

        # [追加] 最後に合計時間を再出力
        content.append(f"\nTotal Execution Time: {elapsed_time:.2f} seconds")
        return content
