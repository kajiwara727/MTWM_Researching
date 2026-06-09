# runners/file_load_runner.py
import json
import os
from .base_runner import BaseRunner
from utils import generate_config_hash
from reporting import (
    save_comparison_summary, 
    save_run_results_to_json, 
    save_run_results_to_text
)

class FileLoadRunner(BaseRunner):
    """
    設定ファイル (CONFIG_LOAD_FILE) からターゲット設定を読み込み、
    最適化を実行する専用のRunner。
    """

    def run(self):
        targets_configs_to_run = []
        
        # 1. Configから読み込むべきファイルパスを取得
        config_path = self.config.CONFIG_LOAD_FILE

        if not config_path:
            raise ValueError("CONFIG_LOAD_FILEが設定されていません。")

        # 2. JSON ファイルの読み込み
        try:
            print(f"Loading configuration from file: {config_path}...")
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not data:
                raise ValueError("設定ファイルが空です。")

            # 3. データの構造解析
            if isinstance(data, list) and len(data) > 0:
                if "targets" in data[0]:
                    # (A) run_name と targets を持つオブジェクトのリスト
                    targets_configs_to_run = data
                elif "ratios" in data[0]:
                    # (B) シンプルなターゲット設定のリスト
                    targets_configs_to_run.append(
                        {"run_name": self.config.RUN_NAME, "targets": data}
                    )
                else:
                    raise ValueError("設定ファイルの構造が無効です。")
            else:
                raise ValueError("設定ファイルの形式が無効です(リストである必要があります)。")

        except FileNotFoundError:
            raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")
        except json.JSONDecodeError:
            raise ValueError(f"JSONデコードエラー: {config_path}")
        except Exception as e:
            raise RuntimeError(f"設定の読み込み中にエラーが発生しました: {e}")

        print(f"Configuration loaded. Found {len(targets_configs_to_run)} pattern(s).")

        all_comparison_results = []
        
        # 4. 出力先ディレクトリ
        base_output_dir = self._get_unique_output_directory_name(
            self.config.RUN_NAME, self.config.RUN_NAME + "_comparison"
        )
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"Results will be saved under: '{base_output_dir}/'")

        # 5. ループ実行
        for run_idx, run_data in enumerate(targets_configs_to_run):
            run_name_prefix = run_data.get("run_name", f"Run_{run_idx+1}")
            targets_config_base = run_data["targets"]

            print(
                f"\n{'='*20} Running Loaded Pattern {run_idx+1}/{len(targets_configs_to_run)} ({run_name_prefix}) {'='*20}"
            )

            # 出力ディレクトリ名
            base_run_name = run_name_prefix + f"_loaded"
            config_hash = generate_config_hash(
                targets_config_base, self.config.OPTIMIZATION_MODE, base_run_name
            )
            output_dir_name = self._get_unique_output_directory_name(
                config_hash, base_run_name
            )
            output_dir = os.path.join(base_output_dir, output_dir_name)

            # 実行エンジン呼び出し
            result = self.engine.run_single_optimization(
                targets_config_base, output_dir, self.config.RUN_NAME
            )

            (final_val, exec_time, ops, reagents, waste) = result

            all_comparison_results.append(
                {
                    "run_name": run_name_prefix,
                    "final_value": final_val,
                    "elapsed_time": exec_time,
                    "total_operations": ops,
                    "total_reagents": reagents,
                    "total_waste": waste,
                    "config": targets_config_base,
                    "objective_mode": self.config.OPTIMIZATION_MODE,
                }
            )

        # 6. 保存
        save_comparison_summary(
            all_comparison_results, base_output_dir, self.config.OPTIMIZATION_MODE
        )
        save_run_results_to_json(all_comparison_results, base_output_dir)
        save_run_results_to_text(all_comparison_results, base_output_dir)

        print("\nAll comparison runs finished successfully.")