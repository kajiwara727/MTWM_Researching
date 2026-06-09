# core/model/problem.py
import itertools
import math
from collections import defaultdict
from utils.config_loader import Config

from utils.helpers import (
    create_intra_key,
    create_inter_key,
    create_peer_key,
)


class MTWMProblem:
    """
    最適化問題の構造を定義するクラス。
    DFMMで計算されたツリー構造に基づき、ノード変数、共有可能性、
    ピア(R)ノードの定義などを行います。
    """

    def __init__(self, targets_config, tree_structures, p_value_maps):
        self.targets_config = targets_config
        self.num_reagents = len(targets_config[0]["ratios"]) if targets_config else 0
        self.tree_structures = tree_structures
        self.p_value_maps = p_value_maps
        
        # 1. 基本的なDFMMノードの骨格を定義
        self.forest = self._define_base_variables()
        
        # 2. ピア(R)ノード（1:1混合）の候補を定義
        self.peer_nodes = self._define_peer_mixing_nodes()
        
        # 3. 共有可能な接続（Potential Sources）を事前計算
        self.potential_sources_map = self._precompute_potential_sources_v2()
        
        # 4. 各ノードに共有変数のプレースホルダーを追加
        self._define_sharing_variables()

    def _define_base_variables(self):
        """
        混合ノードの「骨格」のみを定義します。
        変数の実体は OrToolsSolver が作成します。
        """
        forest_data = []
        for target_idx, tree_structure in enumerate(self.tree_structures):
            tree_data = {}
            levels = sorted({lvl for lvl, _ in tree_structure.keys()})

            for level in levels:
                nodes_at_level = sorted(
                    [
                        node_idx
                        for lvl_node, node_idx in tree_structure.keys()
                        if lvl_node == level
                    ]
                )
                level_nodes = []
                for node_idx in nodes_at_level:
                    # 空の辞書を追加。後に共有変数が格納されます。
                    level_nodes.append({})

                tree_data[level] = level_nodes
            forest_data.append(tree_data)
        return forest_data

    # --- [Refactored & Modified] ピア(R)ノード生成関連メソッド ---

    def _define_peer_mixing_nodes(self):
        """
        設定(PEER_CONNECTION_MODE)に基づいて、
        固定ペア(fixed) または 汎用ノード(dynamic) を定義します。
        """
        print(f"Defining peer-mixing nodes (Mode: {Config.PEER_CONNECTION_MODE})...")
        peer_nodes = []
        
        # 1. 制限モードと上限数の解決
        limit_mode, global_limit = self._resolve_peer_limit_config()

        # 2. 候補ノード情報の収集 (P値ごとにグループ化)
        nodes_by_p_value = self._collect_dfmm_nodes_by_p_value()
        
        # 3. モードによる分岐
        if Config.PEER_CONNECTION_MODE == "dynamic":
            self._create_dynamic_peer_nodes(nodes_by_p_value, limit_mode, global_limit, peer_nodes)
        else:
            self._create_fixed_peer_nodes(nodes_by_p_value, limit_mode, global_limit, peer_nodes)

        # 3b. [一般化] 異重きピア（hetero-weight）の追加（フラグで制御、デフォルトOFF）
        if getattr(Config, "ENABLE_HETERO_PEER", False):
            all_nodes_flat = [n for sublist in nodes_by_p_value.values() for n in sublist]
            self._generate_general_peers(all_nodes_flat, peer_nodes)

        print(f"  -> Created {len(peer_nodes)} peer-mixing nodes.")
        return peer_nodes

    def _create_dynamic_peer_nodes(self, nodes_by_p_value, limit_mode, global_limit, peer_nodes):
        """新ロジック: 候補リストを持つ汎用ノードを生成"""
        total_created = 0
        
        if limit_mode == "half_p_group":
            for p_val, nodes_list in nodes_by_p_value.items():
                if len(nodes_list) < 2: continue
                
                # 候補数の半分(切り捨て)個の汎用ノードを作成
                group_limit = math.floor(len(nodes_list) / 2)
                
                # [Request] 候補数が3の場合は2つ作成する (固定ペアロジックと同様の特例)
                if len(nodes_list) == 3:
                    group_limit = 2
                
                print(f"  -> P-value {p_val}: Creating {group_limit} generic peer node(s) for {len(nodes_list)} candidates.")
                
                for i in range(group_limit):
                    peer_nodes.append({
                        "name": f"peer_gen_p{p_val}_{i}",
                        "p_value": p_val,
                        "candidate_sources": nodes_list, # 候補全リストを持たせる
                        "is_generic": True
                    })
        else:
            # globalモード: 全体リストから上限まで作成
            for p_val, nodes_list in nodes_by_p_value.items():
                if len(nodes_list) < 2: continue
                num_to_make = math.floor(len(nodes_list) / 2)
                # ここでも特例を入れるか検討可能ですが、globalモード全体のバランスのため一旦維持
                
                for i in range(num_to_make):
                    if total_created >= global_limit: return
                    peer_nodes.append({
                        "name": f"peer_gen_p{p_val}_{i}",
                        "p_value": p_val,
                        "candidate_sources": nodes_list,
                        "is_generic": True
                    })
                    total_created += 1

    def _create_fixed_peer_nodes(self, nodes_by_p_value, limit_mode, global_limit, peer_nodes):
        """旧ロジック: Python側でペアを固定してノードを生成"""
        if limit_mode == "half_p_group":
            for p_val, nodes_list in nodes_by_p_value.items():
                if len(nodes_list) < 2: continue
                group_limit = math.floor(len(nodes_list) / 2)
                if len(nodes_list) == 3: group_limit = 2 # 旧ロジックの特例維持
                
                print(f"  -> P-value {p_val}: Creating max {group_limit} fixed peer(s).")
                self._generate_peers_from_list(nodes_list, p_val, group_limit, peer_nodes)
        else:
            all_nodes_flat = [n for sublist in nodes_by_p_value.values() for n in sublist]
            self._generate_peers_from_list(all_nodes_flat, None, global_limit, peer_nodes)

    def _resolve_peer_limit_config(self):
        """Configから制限モードと全体上限値を解決します"""
        limit_config = getattr(Config, "PEER_NODE_LIMIT", "half_targets")
        
        if limit_config == "half_p_group":
            print("  -> Limit Mode: 'half_p_group'. Limiting peers per P-value group.")
            return "half_p_group", float('inf')
            
        num_targets = len(self.targets_config)
        global_limit = float('inf')
        
        if isinstance(limit_config, int):
            global_limit = limit_config
        elif limit_config == "half_targets":
            global_limit = math.floor(num_targets / 2) if num_targets > 0 else 0
            
        print(f"  -> Limit Mode: Global Limit ({global_limit})")
        return "global", global_limit

    def _collect_dfmm_nodes_by_p_value(self):
        """DFMMノードをP値ごとにグループ化して返します"""
        p_groups = defaultdict(list)
        for target_idx, tree in enumerate(self.forest):
            for level, nodes in tree.items():
                if level == 0: continue # ルートノードは除外
                for node_idx, _ in enumerate(nodes):
                    p_val = self.p_value_maps[target_idx].get((level, node_idx))
                    f_val = self.targets_config[target_idx]["factors"][level]
                    
                    # リーフノード (P == F) は除外
                    if p_val is not None and p_val != f_val: 
                        node_id = (target_idx, level, node_idx)
                        p_groups[p_val].append(node_id)
        return p_groups

    def _achievable_pnews(self, p_a, p_b, t, max_cap, a=1, b=1):
        """
        [一般化・達成可能性 / lcmスケール版] 異重きペア (p_a,p_b) を
        体積比 a:b で混合したとき達成可能な p_new（<=max_cap）の集合を返す。
        出力 num[k] = a*(D/p_a)*r_a[k] + b*(D/p_b)*r_b[k], D=lcm(p_a,p_b)。
        sum(num) = (a+b)*D 一定。p_new = (a+b)*D / g。
        a=b=1 のとき従来の 1:1 濃度混合に一致。
        意味ある入力（複数成分が非ゼロ）だけを対象にする。
        """
        from math import gcd, lcm
        from functools import reduce

        def vgcd(v):
            return reduce(gcd, v)

        def ratios_of_weight(p, tt):
            if tt == 1:
                yield (p,)
                return
            for first in range(p + 1):
                for rest in ratios_of_weight(p - first, tt - 1):
                    yield (first,) + rest

        def meaningful(r):
            return sum(1 for x in r if x > 0) >= 2

        D = lcm(p_a, p_b)
        ca, cb = a * (D // p_a), b * (D // p_b)
        total = (a + b) * D
        found = set()
        for d_a in ratios_of_weight(p_a, t):
            if not meaningful(d_a):
                continue
            for d_b in ratios_of_weight(p_b, t):
                if not meaningful(d_b):
                    continue
                num = [ca * d_a[k] + cb * d_b[k] for k in range(t)]
                g = vgcd(num)
                p_new = total // g
                if 2 <= p_new <= max_cap:
                    found.add(p_new)
        return found

    def _enumerate_general_peer_g(self, p_a, p_b, max_mixer_size):
        """
        [一般化 / lcmスケール版] 異重きペアの 1:1濃度混合で、出力重み p_new が
        達成可能な g 候補を列挙する。L=lcm(p_a,p_b), g = 2L / p_new。

        ★原理に基づく絞り込み(セッション15):
          出力重みが入力より大きいと従来手法と変わらず再利用価値がない。
          異重き混合の新規性は「異なる重みを混ぜて入力以下の軽い液滴を作る」点。
          よって p_new <= min(p_a, p_b) のみを候補とする（かつ <= M）。

        ★任意比対応(セッション16): 環境変数 HETERO_RATIOS で体積比を指定可能。
          例 "1:1,2:1,1:2"。各比 (a,b) について達成可能な p_new を列挙する。
          未指定なら 1:1 のみ（従来動作）。
        戻り値: [{"a":a, "b":b, "g": g, "p_new": p_new}, ...]
        """
        from math import lcm
        import os
        L = lcm(p_a, p_b)
        cap = min(max_mixer_size, p_a, p_b)
        # 体積比リストを config から取得（"1:1" のみなら従来の等量混合）
        from utils.config_loader import Config
        ratios_env = getattr(Config, "HETERO_RATIOS", "1:1")
        ratio_list = []
        for tok in ratios_env.split(","):
            tok = tok.strip()
            if ":" in tok:
                aa, bb = tok.split(":")
                ratio_list.append((int(aa), int(bb)))
        cands = []
        seen = set()  # (a,b,p_new) 重複除去
        for (a, b) in ratio_list:
            total = (a + b) * L
            achievable = self._achievable_pnews(p_a, p_b, self.num_reagents, cap, a, b)
            for p_new in sorted(achievable):
                g = total // p_new
                key = (a, b, p_new)
                if key in seen:
                    continue
                seen.add(key)
                cands.append({"a": a, "b": b, "g": g, "p_new": p_new})
        return cands

    def _generate_general_peers(self, all_nodes_flat, out_peer_nodes):
        """
        [一般化] 異重きペア（p_a != p_b）の 1:1濃度混合ピア候補を生成し追加する。
        ★原理に基づく絞り込み:
          - p_new <= min(p_a,p_b)（_enumerate_general_peer_g で実施）= 軽い出力のみ。
          - 環境変数 HETERO_MULTIPLE_ONLY=1 のとき、倍数関係（一方が他方を割り切る）の
            ペアのみ生成（gcd が大きく軽い出力が出やすいため）。
        """
        from utils.config_loader import Config
        from math import gcd
        M = Config.MAX_MIXER_SIZE
        multiple_only = getattr(Config, "HETERO_MULTIPLE_ONLY", False)
        added = 0
        for node_a, node_b in itertools.combinations(all_nodes_flat, 2):
            m_a, l_a, k_a = node_a
            m_b, l_b, k_b = node_b
            p_a = self.p_value_maps[m_a].get((l_a, k_a))
            p_b = self.p_value_maps[m_b].get((l_b, k_b))
            if p_a is None or p_b is None:
                continue
            if p_a == p_b:
                continue  # 等重きは既存ロジックで扱う
            if multiple_only:
                # 倍数関係（大きい方が小さい方の倍数）のペアのみ
                hi, lo = max(p_a, p_b), min(p_a, p_b)
                if hi % lo != 0:
                    continue
            cands = self._enumerate_general_peer_g(p_a, p_b, M)
            for cand in cands:
                entry = self._create_general_peer_entry(
                    node_a, node_b, p_a, p_b, cand["g"], cand["p_new"],
                    cand.get("a", 1), cand.get("b", 1)
                )
                out_peer_nodes.append(entry)
                added += 1
        # 候補数の上限（config の HETERO_PEER_LIMIT、None なら無制限）
        lim = getattr(Config, "HETERO_PEER_LIMIT", None)
        if lim is not None:
            lim = int(lim)
            hetero = [p for p in out_peer_nodes if p.get("is_hetero")]
            non_hetero = [p for p in out_peer_nodes if not p.get("is_hetero")]
            out_peer_nodes[:] = non_hetero + hetero[:lim]
            added = min(added, lim)
        if added:
            print(f"  -> [General] Added {added} hetero-weight peer candidate(s).")

    def _create_general_peer_entry(self, node_a_id, node_b_id, p_a, p_b, g, p_new, a=1, b=1):
        """[一般化 / lcmスケール版] 異重きピアの辞書エントリ。
        入力重み p_a(source_a側), p_b(source_b側), 体積比 a:b, g, 出力重み p_new を保持。
        制約係数 ca=a*L/p_a, cb=b*L/p_b は engine 側で計算する。"""
        (m_a, l_a, k_a) = node_a_id
        (m_b, l_b, k_b) = node_b_id
        if (m_a, l_a, k_a) > (m_b, l_b, k_b):
            node_a_id, node_b_id = node_b_id, node_a_id
            (m_a, l_a, k_a) = node_a_id
            (m_b, l_b, k_b) = node_b_id
            p_a, p_b = p_b, p_a  # 重みも入れ替え（source_a に対応させる）
            a, b = b, a          # 体積比も入れ替え
        name = f"peer_gen_t{m_a}l{l_a}k{k_a}-t{m_b}l{l_b}k{k_b}_p{p_new}_r{a}{b}"
        return {
            "name": name,
            "source_a_id": node_a_id,
            "source_b_id": node_b_id,
            "p_value": p_new,        # 出力重み（固定）
            "is_generic": False,
            "is_hetero": True,        # 異重きピアの目印
            "weight_a": p_a,          # source_a の重み
            "weight_b": p_b,          # source_b の重み
            "ratio_a": a,             # 体積比 a:b の a（source_a 側）
            "ratio_b": b,             # 体積比 a:b の b（source_b 側）
            "coef_g": g,              # g = (a+b)*lcm(weight_a,weight_b)/p_new
        }

    def _generate_peers_from_list(self, nodes_list, p_val_force, limit, out_peer_nodes):
        """
        ノードリストから2つの組み合わせを作成し、条件を満たすものを out_peer_nodes に追加します。
        """
        count = 0
        # itertools.combinations で重複なしのペアを生成
        for node_a, node_b in itertools.combinations(nodes_list, 2):
            if count >= limit:
                break
            
            p_val = p_val_force
            
            # P値が未指定(globalモード)の場合、ここで一致確認を行う
            if p_val is None:
                m_a, l_a, k_a = node_a
                m_b, l_b, k_b = node_b
                p_a = self.p_value_maps[m_a].get((l_a, k_a))
                p_b = self.p_value_maps[m_b].get((l_b, k_b))
                
                if p_a is None or p_a != p_b:
                    continue # P値が一致しないペアはスキップ
                p_val = p_a

            out_peer_nodes.append(self._create_peer_node_entry(node_a, node_b, p_val))
            count += 1

    def _create_peer_node_entry(self, node_a_id, node_b_id, p_val):
        """ヘルパー: ピア(R)ノードの辞書エントリを作成する"""
        (m_a, l_a, k_a) = node_a_id
        (m_b, l_b, k_b) = node_b_id
        
        # ソートして名前を一定にする
        if (m_a, l_a, k_a) > (m_b, l_b, k_b):
            node_a_id, node_b_id = node_b_id, node_a_id
            (m_a, l_a, k_a) = node_a_id
            (m_b, l_b, k_b) = node_b_id

        name = f"peer_mixer_t{m_a}l{l_a}k{k_a}-t{m_b}l{l_b}k{k_b}"
        return {
            "name": name,
            "source_a_id": node_a_id,
            "source_b_id": node_b_id,
            "p_value": p_val,
            "is_generic": False # 固定ペアであることを明示
        }

    # --- 共有（Sharing）関連メソッド ---

    def _precompute_potential_sources_v2(self):
        source_map = {}
        # ... (中略: all_dest_nodes, all_sources の生成ロジックなどは変更なし) ...
        
        all_dest_nodes = [
            (target_idx, level, node_idx)
            for target_idx, tree in enumerate(self.forest)
            for level, nodes in tree.items()
            for node_idx in range(len(nodes))
        ]
        all_dfmm_sources = list(all_dest_nodes)
        all_peer_sources = [("R", i, 0) for i in range(len(self.peer_nodes))]
        all_sources = all_dfmm_sources + all_peer_sources

        for (
            (dst_target_idx, dst_level, dst_node_idx),
            (src_target_idx, src_level, src_node_idx),
        ) in itertools.product(all_dest_nodes, all_sources):
            
            # --- 既存の物理制約チェック (P値, レベル差など) ---
            p_dst = self.p_value_maps[dst_target_idx][(dst_level, dst_node_idx)]
            f_dst = self.targets_config[dst_target_idx]["factors"][dst_level]

            if src_target_idx == "R":
                # Peerノードの場合のチェック (変更なし)
                peer_node = self.peer_nodes[src_level]
                p_src = peer_node["p_value"]
                if peer_node.get("is_generic"):
                    l_src_eff = 999 
                else:
                    l_src_eff = max(
                        peer_node["source_a_id"][1], peer_node["source_b_id"][1]
                    )
                is_valid_level_connection = (l_src_eff > dst_level)
            else:
                # DFMMノードの場合のチェック (変更なし)
                p_src = self.p_value_maps[src_target_idx][(src_level, src_node_idx)]
                l_src_eff = src_level
                if (dst_target_idx, dst_level, dst_node_idx) == (
                    src_target_idx,
                    src_level,
                    src_node_idx,
                ):
                    continue

                is_intermediate_node_connection = (l_src_eff > dst_level)
                is_final_node_connection = (
                    (l_src_eff == 0) and Config.ENABLE_FINAL_PRODUCT_SHARING
                )
                is_valid_level_connection = (
                    is_intermediate_node_connection or is_final_node_connection
                )
            
            if not is_valid_level_connection:
                continue
            
            is_generic_peer = (src_target_idx == "R" and peer_node.get("is_generic", False))
            if not is_generic_peer:
                 if Config.MAX_LEVEL_DIFF is not None and l_src_eff > dst_level + Config.MAX_LEVEL_DIFF:
                    continue
            
            if (p_dst // f_dst) % p_src != 0:
                continue

            # =================================================================
            # [NEW] 役割ベースの接続フィルタリング (Role-Based Pruning)
            # =================================================================
            if Config.ENABLE_ROLE_BASED_PRUNING:
                # 1. Peerノード(R)からの供給は、従来の機能を維持するためプルーニングしない
                if src_target_idx == "R":
                    pass 
                
                # 2. DFMMノード間の接続にはプルーニングを適用
                else:
                    # 親子関係(Default Edge)かどうかを確認 -> 親子なら無条件許可
                    is_default_edge = False
                    if src_target_idx == dst_target_idx:
                         dst_node_struct = self.tree_structures[dst_target_idx].get((dst_level, dst_node_idx))
                         if dst_node_struct and (src_level, src_node_idx) in dst_node_struct['children']:
                             is_default_edge = True
                    
                    if not is_default_edge:
                        is_allowed = False
                        
                        # --- A. 同じターゲット内 (Intra) ---
                        if src_target_idx == dst_target_idx:
                            role_id = (src_node_idx + src_target_idx) % 3
                            
                            # Role 0: 近距離サポーター (直下のみ)
                            if role_id == 0:
                                if (src_level - dst_level) == 1: is_allowed = True
                            # Role 1: 遠距離サポーター (2つ以上離れる)
                            elif role_id == 1:
                                if (src_level - dst_level) > 1: is_allowed = True
                            # Role 2 はIntraには貢献しない

                        # --- B. 異なるターゲット間 (Inter) ---
                        else:
                            mode = Config.INTER_SHARING_MODE
                            
                            if mode == 'ring':
                                # 【リングモード】(Role制限なし)
                                # 次のターゲットであれば、どのノードからでも接続を許可
                                num_targets = len(self.targets_config)
                                if dst_target_idx == (src_target_idx + 1) % num_targets:
                                    is_allowed = True
                                    
                            elif mode == 'linear':
                                # 【リニアモード】(Role制限なし)
                                if dst_target_idx == src_target_idx + 1:
                                    is_allowed = True
                                    
                            else:
                                # 【Allモード】(Role 2 のみ)
                                role_id = (src_node_idx + src_target_idx) % 3
                                if role_id == 2:
                                    is_allowed = True

                        if not is_allowed:
                            continue
            # =================================================================

            key = (dst_target_idx, dst_level, dst_node_idx)
            if key not in source_map:
                source_map[key] = []
            source_map[key].append((src_target_idx, src_level, src_node_idx))
            
        return source_map

    def _create_sharing_vars_for_node(self, dst_target_idx, dst_level, dst_node_idx):
        """
        共有液量を表す変数の「キー」の辞書を作成します。
        """
        potential_sources = self.potential_sources_map.get(
            (dst_target_idx, dst_level, dst_node_idx), []
        )
        intra_vars, inter_vars = {}, {}

        for src_target_idx, src_level, src_node_idx in potential_sources:
            if src_target_idx == dst_target_idx:
                # (ツリー内)
                key_str = create_intra_key(src_level, src_node_idx)
                key = f"from_{key_str}"
                intra_vars[key] = None 
            else:
                if src_target_idx == "R":
                    # (ピア R)
                    key_str = create_peer_key(src_level)
                    key = f"from_{key_str}"
                    inter_vars[key] = None 
                else:
                    # (ツリー間)
                    key_str = create_inter_key(src_target_idx, src_level, src_node_idx)
                    key = f"from_{key_str}"
                    inter_vars[key] = None 
        return intra_vars, inter_vars

    def _define_sharing_variables(self):
        """各ノードの辞書に共有変数のプレースホルダーを追加します"""
        for dst_target_idx, tree_dst in enumerate(self.forest):
            for dst_level, nodes_dst in tree_dst.items():
                for dst_node_idx, node in enumerate(nodes_dst):
                    intra, inter = self._create_sharing_vars_for_node(
                        dst_target_idx, dst_level, dst_node_idx
                    )
                    # node (空の辞書) にキーを追加
                    node["intra_sharing_vars"] = intra
                    node["inter_sharing_vars"] = inter