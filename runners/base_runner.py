# runners/base_runner.py
import os
from abc import ABC, abstractmethod
from core.execution import ExecutionEngine # [NEW]

class BaseRunner(ABC):
    """
    全ての実行モード（ランナー）クラスの親となる抽象基底クラス。
    ExecutionEngine を使用して最適化を実行します。
    """

    def __init__(self, config):
        self.config = config
        self.engine = ExecutionEngine(config)

    @abstractmethod
    def run(self):
        raise NotImplementedError

    def _get_unique_output_directory_name(self, config_hash, base_name_prefix):
        """一意なディレクトリ名を生成します"""
        base_name = f"{base_name_prefix}_{config_hash[:8]}"
        output_dir = base_name
        counter = 1
        while os.path.isdir(output_dir):
            output_dir = f"{base_name}_{counter}"
            counter += 1
        return output_dir

    def _run_single_optimization(self, targets_config_for_run, output_dir, run_name_for_report):
        """
        ExecutionEngine に処理を委譲するラッパーメソッド。
        (既存の子クラスのコードを変更しなくて済むように残しています)
        """
        return self.engine.run_single_optimization(
            targets_config_for_run, output_dir, run_name_for_report
        )