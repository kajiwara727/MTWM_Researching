# runners/permutation_runner.py
import os
import itertools  # 順列や組み合わせを扱うための標準ライブラリ
import copy       # 辞書やリストを深くコピーするために使用
from .base_runner import BaseRunner
from core import find_factors_for_sum, generate_unique_permutations
from utils import generate_config_hash
from reporting import save_permutation_summary  # 専用のサマリー関数


class PermutationRunner(BaseRunner):
    """
    'auto_permutations' モードの実行を担当するクラス。
    
    'factors' の順列の全組み合わせをテストし、最適な階層構造を見つけ出します。
    """

    def run(self):
        # 1. 基本となるターゲット設定を取得 (ratios のみ)
        targets_config_base = self.config.get_targets_config()
        print("Preparing to test all factor permutations...")

        # 2. ベースとなる出力ディレクトリ名を決定
        base_run_name = f"{self.config.RUN_NAME}_permutations"
        config_hash = generate_config_hash(
            targets_config_base, self.config.OPTIMIZATION_MODE, base_run_name
        )
        base_output_dir = self._get_unique_output_directory_name(
            config_hash, base_run_name
        )
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All permutation results will be saved under: '{base_output_dir}/'")

        # 3. 各ターゲットの 'factors' の全順列(Permutation)を計算
        target_perms_options = []
        for target in targets_config_base:
            # まず 'auto' と同様に基本の factors を計算
            base_factors = find_factors_for_sum(
                sum(target["ratios"]), self.config.MAX_MIXER_SIZE
            )
            if base_factors is None:
                raise ValueError(f"Could not determine factors for {target['name']}.")
            
            # [3, 2, 2] から [(3, 2, 2), (2, 3, 2), (2, 2, 3)] などの順列リストを生成
            perms = generate_unique_permutations(base_factors)
            target_perms_options.append(perms)

        # 4. 全ターゲットの「順列リスト」の「直積(product)」を計算
        # 例: T1=[(3,2), (2,3)], T2=[(5,1)] 
        #   -> [ ((3,2), (5,1)), ((2,3), (5,1)) ] という組み合わせリストを生成
        all_config_combinations = list(itertools.product(*target_perms_options))
        
        total_runs = len(all_config_combinations)
        print(f"Found {total_runs} unique factor permutation combinations to test.")

        all_run_results = [] # 全実行結果を保存するリスト

        # 5. 全ての組み合わせをループで実行
        for perm_idx, factor_permutation in enumerate(all_config_combinations):
            print(f"\n{'='*20} Running Combination {perm_idx+1}/{total_runs} {'='*20}")

            # base_config を深くコピーして、今回の組み合わせ用の設定を作成
            current_run_config = copy.deepcopy(targets_config_base)
            perm_name_parts = [] # 出力ディレクトリ名用

            # 各ターゲットに、今回の組み合わせの factors を設定
            for target_idx, target in enumerate(current_run_config):
                current_factors = list(factor_permutation[target_idx])
                target["factors"] = current_factors
                perm_name_parts.append("_".join(map(str, current_factors)))

            # 実行名と出力ディレクトリを決定 (ベースディレクトリの下に作成)
            perm_name = "-".join(perm_name_parts)
            run_name = f"run_{perm_idx+1}_{perm_name}"
            output_dir = os.path.join(base_output_dir, run_name)

            # 6. 単一最適化を実行
            (
                final_value,
                exec_time,
                total_ops,
                total_reagents,
                total_waste,
            ) = self._run_single_optimization(current_run_config, output_dir, run_name)

            # 7. 結果をリストに保存
            all_run_results.append(
                {
                    "run_name": run_name,
                    "targets": copy.deepcopy(current_run_config), # 設定も保存
                    "final_value": final_value,
                    "elapsed_time": exec_time,
                    "total_operations": total_ops,
                    "total_reagents": total_reagents,
                    "total_waste": total_waste,
                    "objective_mode": self.config.OPTIMIZATION_MODE,
                }
            )

        # 8. 全実行が完了したら、専用のサマリー関数を呼び出す
        #    (ベスト/ワーストのパターンなどを集計)
        save_permutation_summary(
            all_run_results, base_output_dir, self.config.OPTIMIZATION_MODE
        )