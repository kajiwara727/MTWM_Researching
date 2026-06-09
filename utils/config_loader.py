# utils/config_loader.py
import config
import scenarios

class Config:
    """設定ファイルとシナリオデータを統合管理するクラス"""
    RUN_NAME = config.RUN_NAME
    MODE = config.FACTOR_EXECUTION_MODE
    OPTIMIZATION_MODE = config.OPTIMIZATION_MODE
    CONFIG_LOAD_FILE = config.CONFIG_LOAD_FILE
    
    ENABLE_VISUALIZATION = config.ENABLE_VISUALIZATION
    MAX_CPU_WORKERS = config.MAX_CPU_WORKERS
    MAX_TIME_PER_RUN_SECONDS = config.MAX_TIME_PER_RUN_SECONDS
    ABSOLUTE_GAP_LIMIT = config.ABSOLUTE_GAP_LIMIT
    
    # --- 制約条件 ---
    MAX_SHARING_VOLUME = config.MAX_SHARING_VOLUME
    MAX_LEVEL_DIFF = config.MAX_LEVEL_DIFF
    MAX_MIXER_SIZE = config.MAX_MIXER_SIZE
    
    MAX_SHARED_INPUTS = getattr(config, "MAX_SHARED_INPUTS", None)
    MAX_TOTAL_REAGENT_INPUT_PER_NODE = getattr(config, "MAX_TOTAL_REAGENT_INPUT_PER_NODE", None)
    PEER_NODE_LIMIT = getattr(config, "PEER_NODE_LIMIT", "half_p_group")
    
    # [NEW] 設定の読み込み (デフォルトは "fixed")
    PEER_CONNECTION_MODE = getattr(config, "PEER_CONNECTION_MODE", "fixed")
    
    ENABLE_FINAL_PRODUCT_SHARING = getattr(config, "ENABLE_FINAL_PRODUCT_SHARING", False)

    # [NEW] プルーニング設定の読み込み
    ENABLE_ROLE_BASED_PRUNING = getattr(config, 'ENABLE_ROLE_BASED_PRUNING', False)
    INTER_SHARING_MODE = getattr(config, 'INTER_SHARING_MODE', 'all')

    # [一般化] 異重きピア(hetero-weight peer)の有効化
    ENABLE_HETERO_PEER = getattr(config, 'ENABLE_HETERO_PEER', False)
    HETERO_RATIOS = getattr(config, 'HETERO_RATIOS', '1:1')
    HETERO_MULTIPLE_ONLY = getattr(config, 'HETERO_MULTIPLE_ONLY', False)
    HETERO_PEER_LIMIT = getattr(config, 'HETERO_PEER_LIMIT', None)
    
    # --- Random設定 ---
    RANDOM_T_REAGENTS = config.RANDOM_T_REAGENTS
    RANDOM_N_TARGETS = config.RANDOM_N_TARGETS
    RANDOM_K_RUNS = config.RANDOM_K_RUNS
    RANDOM_S_RATIO_SUM_SEQUENCE = config.RANDOM_S_RATIO_SUM_SEQUENCE
    RANDOM_S_RATIO_SUM_CANDIDATES = config.RANDOM_S_RATIO_SUM_CANDIDATES
    RANDOM_S_RATIO_SUM_DEFAULT = config.RANDOM_S_RATIO_SUM_DEFAULT

    @staticmethod
    def get_targets_config():
        if Config.MODE in ['auto', 'auto_permutations']:
            return scenarios.TARGETS_FOR_AUTO_MODE
        elif Config.MODE == 'manual':
            return scenarios.TARGETS_FOR_MANUAL_MODE
        elif Config.MODE == 'random' or Config.MODE == 'file_load':
            return []
        else:
            raise ValueError(f"Unknown FACTOR_EXECUTION_MODE: '{Config.MODE}'")