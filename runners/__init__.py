# --- 各実行モード（ランナー）のクラスをインポート ---

# 全てのランナーの基底（親）クラス
from .base_runner import BaseRunner
# 'auto' / 'manual' モード用
from .standard_runner import StandardRunner
# 'random' モード用
from .random_runner import RandomRunner
# 'auto_permutations' モード用
from .permutation_runner import PermutationRunner
# 'file_load' モード用
from .file_load_runner import FileLoadRunner

# --- 実行モード名とランナークラスを紐付ける辞書 ---
# main.py はこの RUNNER_MAP を参照して、config.py のモード設定に
# 応じた適切なランナークラスを決定します。
RUNNER_MAP = {
    "auto": StandardRunner,          # 'auto' が指定されたら StandardRunner を使う
    "manual": StandardRunner,         # 'manual' が指定されたら StandardRunner を使う
    "random": RandomRunner,         # 'random' が指定されたら RandomRunner を使う
    "auto_permutations": PermutationRunner, # 'auto_permutations' が指定されたら PermutationRunner を使う
    "file_load": FileLoadRunner,        # 'file_load' が指定されたら FileLoadRunner を使う
}

# --- このパッケージから import * されたときに公開するものを定義 ---
# (主に 'from runners import *' とした場合に影響)
__all__ = [
    "BaseRunner",
    "StandardRunner",
    "RandomRunner",
    "PermutationRunner",
    "FileLoadRunner",
    "RUNNER_MAP",
]