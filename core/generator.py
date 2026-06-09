import random
import itertools
from core.algorithm.dfmm import find_factors_for_sum, generate_unique_permutations
from core.algorithm.math_utils import generate_random_ratios

class RandomScenarioGenerator:
    """
    RandomRunnerのために、ランダムなターゲット設定（ratios, factors）を生成するクラス。
    """
    def __init__(self, config):
        self.config = config

    def generate_batch_configs(self, num_runs):
        """
        指定された回数(num_runs)分のランダム設定リストを生成して返します。
        実行不可能な設定（factorsが見つからない等）は自動的にスキップされます。
        """
        generated_configs = []
        
        for run_idx in range(num_runs):
            specs = self._determine_specs_for_run()
            run_config = self._create_single_run_config(run_idx, specs)
            
            if run_config:
                generated_configs.append(run_config)
        
        return generated_configs

    def _determine_specs_for_run(self):
        """今回の実行で使用する合計値スペック(S_ratio_sum)を決定"""
        seq = self.config.RANDOM_S_RATIO_SUM_SEQUENCE
        cands = self.config.RANDOM_S_RATIO_SUM_CANDIDATES
        default = self.config.RANDOM_S_RATIO_SUM_DEFAULT
        n_targets = self.config.RANDOM_N_TARGETS

        if seq and len(seq) == n_targets:
            return seq
        elif cands:
            return [random.choice(cands) for _ in range(n_targets)]
        else:
            return [default] * n_targets

    def _create_single_run_config(self, run_idx, specs):
        """単一実行分のターゲット設定リストを作成"""
        targets_list = []
        n_reagents = self.config.RANDOM_T_REAGENTS
        max_mixer = self.config.MAX_MIXER_SIZE

        for t_idx, spec in enumerate(specs):
            # スペックの解析 (dict or int)
            base_sum = spec.get("base_sum", 0) if isinstance(spec, dict) else int(spec)
            multiplier = spec.get("multiplier", 1) if isinstance(spec, dict) else 1

            if base_sum <= 0:
                return None

            try:
                # 比率と因数の生成
                base_ratios = generate_random_ratios(n_reagents, base_sum)
                ratios = [r * multiplier for r in base_ratios]

                base_factors = find_factors_for_sum(base_sum, max_mixer)
                mult_factors = find_factors_for_sum(multiplier, max_mixer)

                if base_factors is None or mult_factors is None:
                    return None

                factors = sorted(base_factors + mult_factors, reverse=True)

                targets_list.append({
                    "name": f"RandomTarget_{run_idx+1}_{t_idx+1}",
                    "ratios": ratios,
                    "factors": factors,
                })

            except ValueError:
                return None # 生成失敗

        return {"run_name": f"run_{run_idx+1}", "targets": targets_list}

class PermutationScenarioGenerator:
    """
    [NEW] 'auto_permutations' モードのために、
    factors の全順列の組み合わせを生成するクラス。
    """
    def __init__(self, config):
        self.config = config

    def generate_permutations(self, base_targets_config):
        """
        ベースとなるターゲット設定から、factorsの順列の全組み合わせを生成します。
        
        Returns:
            list: [{"run_name": ..., "targets": ...}, ...] 形式のリスト
        """
        # 1. 各ターゲットごとに順列リストを作成
        target_perms_options = []
        for target in base_targets_config:
            base_factors = find_factors_for_sum(
                sum(target["ratios"]), self.config.MAX_MIXER_SIZE
            )
            if base_factors is None:
                raise ValueError(f"Could not determine factors for {target['name']}.")
            
            perms = generate_unique_permutations(base_factors)
            target_perms_options.append(perms)

        # 2. 直積（組み合わせ）を計算
        all_combinations = list(itertools.product(*target_perms_options))
        
        # 3. 実行用設定オブジェクトのリストに変換
        scenarios = []
        for idx, combo in enumerate(all_combinations):
            # ベース設定をコピー
            import copy
            current_targets = copy.deepcopy(base_targets_config)
            
            # ディレクトリ名用のパーツ
            name_parts = []
            
            # 各ターゲットに今回の順列を適用
            for t_idx, target in enumerate(current_targets):
                factors_tuple = combo[t_idx]
                target["factors"] = list(factors_tuple)
                name_parts.append("_".join(map(str, factors_tuple)))

            perm_name = "-".join(name_parts)
            run_name = f"perm_{idx+1}_{perm_name}"
            
            scenarios.append({
                "run_name": run_name,
                "targets": current_targets
            })
            
        return scenarios