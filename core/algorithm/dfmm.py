import math
import itertools
from functools import reduce
import operator


def find_factors_for_sum(ratio_sum, max_factor):
    """
    DFMM (Digital Microfluidic Mixing) アルゴリズムに基づき、比率の合計値（ratio_sum）を
    指定された最大値（max_factor、config.MAX_MIXER_SIZE）以下の因数の積に分解します。
    これは、混合ツリーの階層構造を決定するために使用されます。

    (例: ratio_sum=18, max_factor=5 -> [3, 3, 2] ※積が18になり、全て5以下)

    Args:
        ratio_sum (int): 分解対象となる比率の合計値。
        max_factor (int): 許容される因数の最大値。

    Returns:
        list[int] or None: 見つかった因数のリスト（降順ソート済み）。見つからない場合はNone。
    """
    if ratio_sum <= 1:
        # 合計が1以下の場合は、分解不要
        return []

    remaining_sum, factors = ratio_sum, []

    # remaining_sum が 1 になるまで（素因数分解のように）因数で割り続ける
    while remaining_sum > 1:
        found_divisor = False
        
        # 効率化のため、大きな因数(max_factor)から試す
        for divisor in range(max_factor, 1, -1):
            if remaining_sum % divisor == 0:
                # 割り切れた場合
                factors.append(divisor)      # 因数をリストに追加
                remaining_sum //= divisor    # remaining_sum を割った値で更新
                found_divisor = True
                break # 次の while ループに移る
                
        # どの因数でも割り切れなかった場合 (例: 素数が残ったが max_factor より大きい)
        if not found_divisor:
            print(
                f"Error: Could not find factors for sum {ratio_sum}. Failed at {remaining_sum}."
            )
            return None # 分解は不可能

    # 見つかった因数を降順 (例: [5, 3, 2]) にソートして返す
    return sorted(factors, reverse=True)


def generate_unique_permutations(factors):
    """
    因数のリストから、重複を考慮したユニークな順列をすべて生成します。
    'auto_permutations' モードで、最適な混合階層の順序を探索するために使用されます。

    (例: [3, 3, 2] -> [(3, 3, 2), (3, 2, 3), (2, 3, 3)])

    Args:
        factors (list[int]): 因数のリスト。

    Returns:
        list[tuple]: 生成されたユニークな順列のリスト。
    """
    if not factors:
        return [()]
    
    # itertools.permutations ですべての順列を生成
    # set() を使うことで、同じ順列が複数回現れるのを防ぐ (例: [3, 3, 2] など)
    return list(set(itertools.permutations(factors)))


def build_dfmm_forest(targets_config):
    """
    DFMMアルゴリズムに基づき、各ターゲットの混合ツリー構造（親子関係）を構築します。
    複数のターゲットのツリーをまとめて「森 (forest)」として扱います。

    Args:
        targets_config (list[dict]): 各ターゲットの設定（'ratios', 'factors'を含む）のリスト。

    Returns:
        list[dict]: 各ツリーのノードと親子関係を格納した辞書のリスト（フォレスト）。
                       各辞書のキーは (level, node_idx) タプル、
                       値は {'children': list[tuple]} 形式。
    """
    forest_structure = [] # 結果を格納するリスト
    
    # --- 各ターゲット（ツリー）ごとにループ ---
    for target in targets_config:
        ratios, factors = target["ratios"], target["factors"]
        num_levels = len(factors) # 階層の深さ

        tree_structure = {} # このツリーの構造
        
        # 最初は最下層（leaf node）の入力として試薬の比率を扱う
        values_to_process = list(ratios) # (例: [2, 11, 5])
        
        # 下位レベルから上がってきたノードID (level, node_idx) のリスト
        # (最初は空)
        child_node_ids = [] 

        # --- 混合ツリーを下のレベル（leaf）から上のレベル（root）へと構築していく ---
        # level は (num_levels - 1) (例: 2) から 0 (root) へと進む
        # factors = [3, 2, 3] (len=3)
        # level 2 (factor=3), level 1 (factor=2), level 0 (factor=3) の順
        for level in range(num_levels - 1, -1, -1):
            current_factor = factors[level] # このレベルの混合比 (ミキサーサイズ)

            # 現在のレベルでの混合操作における「余り」と「商」を計算
            # (例: level 2, factor=3, values=[2, 11, 5])
            
            # 余り: このレベルで直接投入される試薬量に対応
            # (例: [2 % 3, 11 % 3, 5 % 3] -> [2, 2, 2])
            level_remainders = [v % current_factor for v in values_to_process]
            
            # 商: このレベルの出力となり、上位レベルへの入力となる量に対応
            # (例: [2 // 3, 11 // 3, 5 // 3] -> [0, 3, 1])
            level_quotients = [v // current_factor for v in values_to_process]

            # 現在のレベルで必要となるノード（ミキサー）の数を計算
            # 入力は、(1) このレベルで直接投入される試薬(余り) と
            # (2) 下位レベルから上がってきた中間液(子ノード数) の合計
            # (例: level 2 (初回) -> sum([2, 2, 2]) + len([]) = 6)
            total_inputs_at_level = sum(level_remainders) + len(child_node_ids)

            # 必要なミキサー数 = ceil(総入力 / 現在レベルの因数)
            # (例: ceil(6 / 3) = 2)
            num_nodes_at_level = (
                math.ceil(total_inputs_at_level / current_factor)
                if total_inputs_at_level > 0
                else 0
            )
            
            # このレベルに存在するノードIDのリスト (例: [(2, 0), (2, 1)])
            current_level_node_ids = [(level, k) for k in range(num_nodes_at_level)]

            # ノードをツリー構造に追加 (初期状態では子は空リスト)
            for node_id in current_level_node_ids:
                tree_structure[node_id] = {"children": []}

            # 下のレベルからのノード（子）を、現在のレベルのノード（親）に均等に接続
            if num_nodes_at_level > 0:
                parent_node_idx_counter = 0 # 親ノードのインデックス (0, 1, 0, 1, ...)
                
                # 各子ノードIDについてループ
                for child_id in child_node_ids:
                    # ラウンドロビンで割り当てる親ノードIDを取得 (例: (2, 0))
                    parent_node_id = current_level_node_ids[parent_node_idx_counter]
                    
                    # 親ノードの 'children' リストに子ノードIDを追加
                    tree_structure[parent_node_id]["children"].append(child_id)
                    
                    # 次の親ノードのインデックスへ (循環させる)
                    # (例: (0 + 1) % 2 -> 1)
                    # (例: (1 + 1) % 2 -> 0)
                    parent_node_idx_counter = (parent_node_idx_counter + 1) % num_nodes_at_level

            # --- 次の（一つ上の）レベルの計算準備 ---
            
            # 現在レベルのノード ([(2, 0), (2, 1)]) が、次のレベルの子ノードとなる
            child_node_ids = current_level_node_ids
            
            # 現在レベルの商 ([0, 3, 1]) が、次のレベルで処理される値となる
            values_to_process = level_quotients

        # ターゲットのツリーが完成したら、フォレストに追加
        forest_structure.append(tree_structure)
        
    return forest_structure


def calculate_p_values_from_structure(forest_structure, targets_config):
    """
    構築されたツリー構造に基づき、各ノードの「P値」を再帰的に計算します。
    P値は、そのノードが担当する混合液の相対的な「単位量」を表し、濃度計算の制約に不可欠です。

    Args:
        forest_structure (list[dict]): build_dfmm_forestで構築されたフォレスト。
        targets_config (list[dict]): 各ターゲットの設定リスト。

    Returns:
        list[dict]: 各ツリーのノードとそのP値を格納した辞書のリスト (p_value_maps)。
                    各辞書のキーは (level, node_idx) タプル、値は P値 (int)。
    """
    p_value_maps = []
    
    # --- 各ターゲット（ツリー）ごとにループ ---
    for target_idx, tree_structure in enumerate(forest_structure):
        factors = targets_config[target_idx]["factors"] # (例: [3, 2, 3])
        p_value_cache = {} # 計算結果のメモ化（キャッシュ）用
        p_value_map = {}   # このツリーのP値マップ

        def prod(iterable):
            """イテラブルなオブジェクトの要素の積を計算するヘルパー関数。"""
            return reduce(operator.mul, iterable, 1)

        def get_p_for_node(node_id):
            """メモ化再帰を用いて、特定のノードのP値を計算する。"""
            
            # 1. キャッシュにあればそれを返す
            if node_id in p_value_cache:
                return p_value_cache[node_id]

            level, k = node_id # (例: (1, 0))
            
            # 2. 子ノードを取得 (存在しない場合は空リスト)
            children = tree_structure.get(node_id, {}).get("children", [])

            # 3. P値を計算
            if not children:
                # 子がいない場合（最下層に近いノード、または試薬のみから成るノード）
                # P値は、そのレベル「以降」(level=1 なら [2, 3]) のfactorの積
                # (例: factors = [3, 2, 3], level=1 -> prod([2, 3]) = 6)
                # (例: factors = [3, 2, 3], level=2 -> prod([3]) = 3)
                p_value = prod(factors[level:])
            else:
                # 子がいる場合
                # P値は「子のP値の最大値」に「そのレベルのfactor」を掛けたもの
                
                # まず、子のP値を再帰的に計算し、その最大値を取得
                max_child_p = max(get_p_for_node(child_id) for child_id in children)
                
                # (例: level=0, factor=3, max_child_p=6 -> 6 * 3 = 18)
                p_value = max_child_p * factors[level]

            # 4. 計算結果をキャッシュして返す
            p_value_cache[node_id] = p_value
            return p_value

        # --- ツリー内の全ノードに対してP値を計算 ---
        for node_id in tree_structure:
            p_value_map[node_id] = get_p_for_node(node_id)

        p_value_maps.append(p_value_map)

    return p_value_maps

def apply_auto_factors(targets_config, max_mixer_size):
    """
    ターゲット設定のリストを受け取り、'auto'モード用に
    各ターゲットの factors を計算して埋め込みます。
    """
    for target in targets_config:
        ratio_sum = sum(target["ratios"])
        factors = find_factors_for_sum(ratio_sum, max_mixer_size)
        
        if factors is None:
            raise ValueError(f"Could not determine factors for {target['name']} (Sum={ratio_sum}).")
            
        target["factors"] = factors
    return targets_config