# config.py

# 実行名を定義します。出力ディレクトリの名前の一部として使用されます。
RUN_NAME = "PowerPoint_125_Unlimit_ROLEBASED_ALL"

# 実行モード: 'manual', 'auto', 'auto_permutations', 'random', 'file_load'
FACTOR_EXECUTION_MODE = "manual"

# 最適化の目的: "waste", "operations", "reagents"
OPTIMIZATION_MODE = "waste"

# --- 出力設定 ---
ENABLE_VISUALIZATION = False # True or False
CONFIG_LOAD_FILE = "random_configs.json"

# --- 制約条件 (ソルバーの挙動制御) ---
MAX_CPU_WORKERS = 32
MAX_TIME_PER_RUN_SECONDS = 120
ABSOLUTE_GAP_LIMIT = 0.99
MAX_SHARING_VOLUME = None
MAX_SHARED_INPUTS = None
MAX_TOTAL_REAGENT_INPUT_PER_NODE = None
MAX_LEVEL_DIFF = None
MAX_MIXER_SIZE = 5

PEER_NODE_LIMIT = "half_p_group"

# ペア混合ノードの接続モード
# "fixed"   : 従来の方式 (Python側で事前にペアを固定する)
# "dynamic" : 新方式 (ソルバーが候補の中から最適な2つを選択する)
PEER_CONNECTION_MODE = "fixed" 

ENABLE_FINAL_PRODUCT_SHARING = False

# [NEW] 役割ベースのプルーニング設定 (DFMMノード間の接続削減)
# True : 各ノードに役割を与え、Intra接続を制限する (高速化)
# False: 可能なすべてのノードを接続候補とする (厳密解)
ENABLE_ROLE_BASED_PRUNING = False

# [NEW] Inter-Sharing（他ターゲットへの供給）の接続モード
# 'all'   : 全ターゲットへ接続 (役割Role2による制限あり)
# 'ring'  : 次のターゲットへ循環接続 (制限なし・確実につながる) [推奨]
# 'linear': 一方向接続 (最後は戻らない)
INTER_SHARING_MODE = 'all'

# --- 'random' モード用パラメータ ---
RANDOM_N_TARGETS = 3
RANDOM_T_REAGENTS = 3
RANDOM_K_RUNS = 30
RANDOM_S_RATIO_SUM_DEFAULT = 125

# --- 混合比和の生成ルール（以下のいずれか1つが使用されます） ---
# 以下の設定は、`runners/random_runner.py` によって上から順に評価され、
# 最初に有効な（空でない）設定が1つだけ採用されます。

# オプション1: 固定シーケンス
# `RANDOM_N_TARGETS` と要素数を一致させる必要があります。
# (例: [18, {'base_sum': 18, 'multiplier': 5}, 18, 24])
# これが空でないリストの場合、この設定が使用されます。
RANDOM_S_RATIO_SUM_SEQUENCE = [
   #  18, {'base_sum': 18, 'multiplier': 5}, 18
]

# オプション2: 候補リストからのランダム選択
# `RANDOM_S_RATIO_SUM_SEQUENCE` が空のリストの場合、こちらが評価されます。
# (例: [18, 24, 30, 36])
# これが空でないリストの場合、ターゲットごとにこのリストからランダムに値が選ばれます。
RANDOM_S_RATIO_SUM_CANDIDATES = [
    # 18, 24, 30, 36
]
# ============================================================
# [一般化] 異重きピア(hetero-weight peer)の設定
# ============================================================
# 異重きピア(異なる重みの中間液滴を混合して再利用する)を有効にするか
ENABLE_HETERO_PEER = True

# 混合の体積比リスト。"1:1" のみなら従来の等量混合。
# "1:1,2:1,1:2" のように複数指定すると、各比での混合候補を生成する
# (削減ケースが増えるが候補数も増える)。
HETERO_RATIOS = "1:1,2:1,1:2"

# True のとき、重みが倍数関係(一方が他方を割り切る)のペアのみを候補にする。
# 候補数を大幅に減らせて、効果はほぼ維持される(推奨)。
HETERO_MULTIPLE_ONLY = True

# 異重きピア候補の最大数。None なら無制限。
# 候補が多すぎてソルバーが重いときに制限する。
HETERO_PEER_LIMIT = None

# ★出力重み(p_new)の上限の決め方を切り替える。
#   "min"  : p_new <= min(p_a, p_b)  [現状・従来の動作]
#            小さい方の入力以下。軽い液滴のみを候補にする。
#   "max"  : p_new <= max(p_a, p_b) かつ DFMM既存重み(中間+リーフ)に含まれるもののみ
#            大きい方の入力以下で、材料になる(既存の)重みだけを候補にする。
# 両者で結果がどう変わるか比較するために切り替え可能にしている。
HETERO_PNEW_CAP_MODE = "min"