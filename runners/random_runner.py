# runners/random_runner.py
import os
import json
from .base_runner import BaseRunner
from core.generator import RandomScenarioGenerator
from reporting import (
    save_random_run_summary, 
    save_run_results_to_json, 
    save_run_results_to_text 
)

class RandomRunner(BaseRunner):
    """
    'random' モードの実行を担当するクラス。
    シナリオ生成は Generator に委譲し、実行エンジンを使用して最適化ループを回します。
    """

    def run(self):
        """'random' モードのメイン実行ロジック"""
        num_runs = self.config.RANDOM_K_RUNS
        print(f"Preparing to run {num_runs} random simulations...")

        # 1. 出力ディレクトリの準備
        # フォルダ名用の文字列生成ロジックはシンプルに
        base_run_name = f"{self.config.RUN_NAME}-random-{num_runs}runs"
        base_output_dir = self._get_unique_output_directory_name("random", base_run_name)
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"Results will be saved under: '{base_output_dir}/'")

        # 2. シナリオ生成 (Generatorに委譲)
        generator = RandomScenarioGenerator(self.config)
        scenarios = generator.generate_batch_configs(num_runs)
        
        print(f"Successfully generated {len(scenarios)} valid scenarios.")

        all_run_results = []
        saved_configs = []

        # 3. 実行ループ
        for i, scenario in enumerate(scenarios):
            run_name = scenario["run_name"]
            targets = scenario["targets"]
            
            print(f"\n{'='*20} Running Random Simulation {i+1}/{len(scenarios)} ({run_name}) {'='*20}")
            
            output_dir = os.path.join(base_output_dir, run_name)
            
            # 実行エンジン呼び出し (BaseRunner経由ではなく直接 engine を呼ぶ形でもOKですが、
            # BaseRunner.engine があるのでそれを使います)
            result = self.engine.run_single_optimization(targets, output_dir, run_name)
            
            # 結果を展開
            (final_val, exec_time, ops, reagents, waste) = result
            
            # 結果リストに追加
            all_run_results.append({
                "run_name": run_name,
                "config": targets,
                "final_value": final_val,
                "elapsed_time": exec_time,
                "total_operations": ops,
                "total_reagents": reagents,
                "total_waste": waste,
                "objective_mode": self.config.OPTIMIZATION_MODE,
            })
            saved_configs.append(scenario)

        # 4. サマリーと設定の保存
        # 既存のサマリー (集計含む)
        save_random_run_summary(all_run_results, base_output_dir)
        
        # JSON形式の保存
        save_run_results_to_json(all_run_results, base_output_dir)
        
        # テキスト形式のリスト保存
        save_run_results_to_text(all_run_results, base_output_dir)
        
        # コンフィグ保存
        config_log_path = os.path.join(base_output_dir, "random_configs.json")
        with open(config_log_path, "w", encoding="utf-8") as f:
            json.dump(saved_configs, f, indent=4)
        print(f"\nAll configurations saved to: {config_log_path}")