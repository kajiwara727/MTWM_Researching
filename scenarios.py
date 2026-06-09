# --- 'auto' / 'auto_permutations' モード用設定 ---
# 'auto'系モードでは、'factors' (混合階層) を指定する必要はありません。
# 'ratios' (混合比率) のみ定義します。
TARGETS_FOR_AUTO_MODE = [
    # 分析用
    {'name': 'Target 1', 'ratios': [9, 25, 43, 58]},
    {'name': 'Target 2', 'ratios': [19, 65, 17, 34]},
    {'name': 'Target 1', 'ratios': [69, 3, 35, 28]},
    {'name': 'Target 2', 'ratios': [56, 67, 7, 5]},

    # Def[135]-2-3-2回目
    # {'name': 'Target 1', 'ratios': [121,2,12]},
    # {'name': 'Target 2', 'ratios': [9,32,94]},

    # Simple
    # {'name': 'Target 1', 'ratios': [2,11,5]},
    # {'name': 'Target 2', 'ratios': [12,5,1]},
    # {'name': 'Target 3', 'ratios': [5,6,14]}

     # すべて12:12:1の場合
    # {'name': 'Target 1', 'ratios': [12,12,1]},
    # {'name': 'Target 2', 'ratios': [12,12,1]},
    # {'name': 'Target 3', 'ratios': [12,12,1]}

    # すべて97:97:6の場合
    # {'name': 'Target 1', 'ratios': [97,97,6]},
    # {'name': 'Target 2', 'ratios': [97,97,6]},
    # {'name': 'Target 3', 'ratios': [97,97,6]}

     # すべて49:49:2の場合
    # {'name': 'Target 1', 'ratios': [49,49,2]},
    # {'name': 'Target 2', 'ratios': [49,49,2]},
    # {'name': 'Target 3', 'ratios': [49,49,2]}

    # 49:98:147
    # {'name': 'Target 1', 'ratios': [26,10,13]},
    # {'name': 'Target 2', 'ratios': [53,20,25]},
    # {'name': 'Target 3', 'ratios': [79,30,38]},

    # 49:98:147_Second
    # {'name': 'Target 1', 'ratios': [23,13,13]},
    # {'name': 'Target 2', 'ratios': [46,27,25]},
    # {'name': 'Target 3', 'ratios': [69,40,38]},

    # 49:98:147_Third
    # {'name': 'Target 1', 'ratios': [19,17,13]},
    # {'name': 'Target 2', 'ratios': [40,33,25]},
    # {'name': 'Target 3', 'ratios': [59,50,38]},

    # TimeTest
    # {'name': 'Target 1', 'ratios': [2, 12,3,1]},
    # {'name': 'Target 2', 'ratios': [5,3,4,6]},
    # {'name': 'Target 3', 'ratios': [7,3,7,1]},
    # {'name': 'Target 4', 'ratios': [9,2,6,1]},
    # {'name': 'Target 5', 'ratios': [13,1,1,3]},

    # {'name': 'Target 2', 'ratios': [93,21,21]},
    # {'name': 'Target 3', 'ratios': [46,74,15]},
    # {'name': 'Target 3', 'ratios': [3, 5, 10]},
    # {'name': 'Target 4', 'ratios': [7, 7, 4]},
    # {'name': 'Target 2', 'ratios': [60, 25, 5]},
    # {'name': 'Target 4', 'ratios': [6, 33, 36]},
    # {'name': 'Target 1', 'ratios': [102, 26, 3, 3, 122]},
    # {'name': 'Target 1', 'ratios': [15, 18, 42]}
]

# --- 'manual' モード用設定 ---
# 'manual' モードでは、'ratios' に加えて 'factors' を明示的に指定する必要があります。
# 'factors' の積は、'ratios' の合計値と一致する必要があります。
# また、'factors' の各要素は MAX_MIXER_SIZE 以下でなければなりません。
TARGETS_FOR_MANUAL_MODE = [
    # === 異重きピア純粋検証 (等重きペアなし・異重き6×9のみ、lcm修正後再試行) ===
    {'name': 'A', 'ratios': [7,7,4], 'factors': [3, 3, 2]},  # 重み6
    {'name': 'B', 'ratios': [9,25,2], 'factors': [3, 3, 2,2]},  # 重み9

    # === Fig.6系派生 (重み6×2 + 重み9) ===
    # {'name': 'A', 'ratios': [15, 1, 2], 'factors': [3, 3, 2]},
    # {'name': 'B', 'ratios': [8, 1, 9],  'factors': [3, 3, 2]},
    # {'name': 'C', 'ratios': [20, 4, 3], 'factors': [3, 3, 3]},

    # === 軽い異重きペア検証 (重み4,6,12が共存) ===
    # {'name': 'A', 'ratios': [10, 9, 5], 'factors': [2, 2, 3, 2]},
    # {'name': 'B', 'ratios': [7, 11, 6], 'factors': [2, 3, 2, 2]},

    # === 異重きピア純粋検証 (等重きペアなし・異重き6×9のみ) ===
    # {'name': 'A', 'ratios': [15, 1, 2], 'factors': [3, 3, 2]},
    # {'name': 'B', 'ratios': [20, 4, 3], 'factors': [3, 3, 3]},

    # === 異重きピア検証ケース (sum混在で重み4,6が共存) ===
    # {'name': 'A', 'ratios': [15, 1, 2], 'factors': [3, 3, 2]},
    # {'name': 'B', 'ratios': [5, 6, 1],  'factors': [3, 2, 2]},
    # {'name': 'C', 'ratios': [1, 8, 3],  'factors': [3, 2, 2]},

    # === Fig.6 再現ケース (論文: MTWM nw=5 / 提案 nw=2) ===
    # {'name': 'T1', 'ratios': [15, 1, 2], 'factors': [3, 3, 2]},
    # {'name': 'T2', 'ratios': [8, 1, 9], 'factors': [3, 3, 2]},
    # {'name': 'T3', 'ratios': [1, 8, 9], 'factors': [3, 3, 2]},

    # {'name': 'Target 1', 'ratios': [23,13,13]},
    # {'name': 'Target 2', 'ratios': [46,27,25]},
    # {'name': 'Target 3', 'ratios': [69,40,38]},

    # 49:98:147_Second
    # {'name': 'Target 1', 'ratios': [23,13,13], 'factors': [7,7]},
    # {'name': 'Target 2', 'ratios': [46,27,25], 'factors': [7,2,7]},
    # {'name': 'Target 3', 'ratios': [69,40,38], 'factors': [7,3,7]},

    # {'name': 'Target 1', 'ratios': [6, 33, 15], 'factors': [3, 3, 3, 2]},
    # {'name': 'Target 1', 'ratios': [2, 3, 7], 'factors': [3, 2, 2]},
    # {'name': 'Target 2', 'ratios': [1, 5, 6], 'factors': [3, 2, 2]},
    # {'name': 'Target 3', 'ratios': [4, 3, 5], 'factors': [3, 2, 2]},
    # {'name': 'Target 3', 'ratios': [4, 5, 9], 'factors': [3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [3, 5, 10], 'factors': [3, 3, 2]},
    # {'name': 'Target 4', 'ratios': [7, 7, 4], 'factors': [3, 3, 2]},
    # {'name': 'Target 2', 'ratios': [60, 25, 5], 'factors': [5, 3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [5, 6, 14], 'factors': [5, 5]},
    # {'name': 'Target 4', 'ratios': [6, 33, 36], 'factors': [3, 5, 5]},
    # {'name': 'Target 1', 'ratios': [102, 26, 3, 3, 122], 'factors': [4, 4, 4, 4]},
    # {"name": "Target 1", "ratios": [2, 11, 5], "factors": [3, 3, 2]},
    # {'name': 'Target 2', 'ratios': [12, 5, 1], 'factors': [3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [5, 6, 14], 'factors': [5, 5]},
    # {'name': 'Target 1', 'ratios': [10, 55, 25], 'factors': [5, 3, 3, 2]},
    # {"name": "Target 2", "ratios": [60, 25, 5], "factors": [5, 3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [15, 18, 42], 'factors': [3, 5, 5]}
]