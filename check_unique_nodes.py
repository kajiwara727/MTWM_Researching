import math
import sys
import os
import copy

# プロジェクトルートへのパスを通す
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.algorithm.dfmm import find_factors_for_sum
from scenarios import TARGETS_FOR_AUTO_MODE, TARGETS_FOR_MANUAL_MODE

# 設定: どちらのシナリオをチェックするか ("auto", "manual", "all")
CHECK_MODE = "all" 
MAX_MIXER_SIZE = 5

# --- 出力先設定 ---
OUTPUT_FILE = "uniqueness_analysis_result.txt"

class DualLogger:
    """
    標準出力（コンソール）とファイルの双方にメッセージを出力するためのクラス
    """
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "w", encoding='utf-8')

    def write(self, message):
        self.terminal.write(message) # 画面に出力
        self.log.write(message)      # ファイルに出力

    def flush(self):
        # リアルタイム反映のためにflushを行う
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()

def analyze_unique_reagent_allocation(target_config):
    """
    ターゲット設定を受け取り、DFMMロジックに従ってツリーを構築しつつ、
    各ノードの試薬割り当てが「一意に決まるか」を判定する。
    """
    name = target_config.get('name', 'Unknown Target')
    ratios = target_config['ratios']
    factors = target_config.get('factors')

    print(f"\n{'='*60}")
    print(f" Analysis for: {name}")
    print(f" Ratios: {ratios}")
    print(f" Factors: {factors}")
    print(f"{'='*60}")

    if not factors:
        print("Error: Factors are missing for this target.")
        return

    num_levels = len(factors)
    values_to_process = list(ratios)
    child_node_ids = [] # (level, index) のリスト

    # 下のレベルから上のレベルへシミュレーション
    for level in range(num_levels - 1, -1, -1):
        current_factor = factors[level]
        
        # 1. このレベルでの計算
        level_remainders = [v % current_factor for v in values_to_process]
        level_quotients = [v // current_factor for v in values_to_process]
        
        total_inputs = sum(level_remainders) + len(child_node_ids)
        num_nodes = math.ceil(total_inputs / current_factor) if total_inputs > 0 else 0
        
        # 試薬の種類数を確認
        active_reagents_indices = [i for i, val in enumerate(level_remainders) if val > 0]
        num_active_reagents_types = len(active_reagents_indices)
        
        # ノードごとの空き容量計算
        nodes_needing_reagents = []
        node_capacities = []
        
        for k in range(num_nodes):
            if num_nodes > 0:
                num_children = (len(child_node_ids) // num_nodes) + (1 if k < (len(child_node_ids) % num_nodes) else 0)
            else:
                num_children = 0
            
            slots_needed = current_factor - num_children
            node_capacities.append(slots_needed)
            
            if slots_needed > 0:
                nodes_needing_reagents.append(k)

        print(f"\n[Level {level}] (Factor: {current_factor})")
        print(f"  - Reagents to add (Remainders): {level_remainders} (Total: {sum(level_remainders)})")
        print(f"  - Nodes at this level: {num_nodes}")
        
        # --- 判定ロジック ---
        for k in range(num_nodes):
            node_name = f"Node_l{level}_k{k}"
            slots_needed = node_capacities[k]
            
            is_unique = False
            reason = ""

            if slots_needed == 0:
                is_unique = True
                reason = "Full with children (Capacity 0)"
            elif len(nodes_needing_reagents) == 1 and k in nodes_needing_reagents:
                is_unique = True
                reason = "Sole receiver at this level"
            elif num_active_reagents_types <= 1:
                is_unique = True
                reason = "Mono-reagent source (Only 1 type available)"
            
            status_icon = "✅ UNIQUE" if is_unique else "⚠️ AMBIGUOUS"
            print(f"  {node_name:<15}: {status_icon} | Slots needed: {slots_needed} | {reason}")
            
            if not is_unique:
                print(f"      -> Must decide how to distribute: {level_remainders}")

        child_node_ids = [(level, k) for k in range(num_nodes)]
        values_to_process = level_quotients

def prepare_targets():
    """scenarios.py からターゲットリストを作成する"""
    targets_to_check = []

    if CHECK_MODE in ["manual", "all"]:
        print(f"Loading {len(TARGETS_FOR_MANUAL_MODE)} manual targets...")
        targets_to_check.extend(copy.deepcopy(TARGETS_FOR_MANUAL_MODE))

    if CHECK_MODE in ["auto", "all"]:
        print(f"Loading {len(TARGETS_FOR_AUTO_MODE)} auto targets...")
        auto_targets = copy.deepcopy(TARGETS_FOR_AUTO_MODE)
        
        for t in auto_targets:
            if 'factors' not in t:
                s = sum(t['ratios'])
                f = find_factors_for_sum(s, MAX_MIXER_SIZE)
                if f is None:
                    print(f"Skipping {t['name']}: Could not find factors for sum {s}")
                    continue
                t['factors'] = f
            targets_to_check.append(t)
            
    return targets_to_check

if __name__ == "__main__":
    # --- ロガーのセットアップ ---
    # sys.stdout を DualLogger に置き換えることで、全ての print 文を
    # コンソールとファイルの両方に書き込むようにする。
    original_stdout = sys.stdout
    logger = DualLogger(OUTPUT_FILE)
    sys.stdout = logger

    try:
        print("--- Checking Reagent Allocation Uniqueness from scenarios.py ---")
        print(f"Output will be saved to: {os.path.abspath(OUTPUT_FILE)}\n")
        
        # ターゲットリストの準備
        config = prepare_targets()
        
        if not config:
            print("No targets found to check. Please check scenarios.py or CHECK_MODE.")
        else:
            # 各ターゲットについて分析を実行
            for target in config:
                analyze_unique_reagent_allocation(target)
                
    except Exception as e:
        print(f"\nAn error occurred during execution: {e}")
        raise e
    finally:
        # 終了処理: 標準出力を元に戻し、ファイルを閉じる
        sys.stdout = original_stdout
        logger.close()
        print(f"\nDone. Analysis saved to {OUTPUT_FILE}")
