import os
import networkx as nx  # グラフ構造の作成・操作
import matplotlib.pyplot as plt # グラフの描画
import matplotlib.colors as mcolors # 色の正規化
from utils import create_dfmm_node_name, parse_sharing_key


class SolutionVisualizer:
    """
    ソルバーの解（OrToolsSolutionModel）を読み取り、networkxでグラフを構築し、
    matplotlibで可視化（PNG画像として保存）するクラス。
    """

    # --- グラフのスタイル設定 ---
    STYLE_CONFIG = {
        "mix_node": {"color": "#87CEEB", "size": 2000},       # 水色: 中間ノード
        "target_node": {"color": "#90EE90", "size": 2000},    # 緑: 最終ターゲット (level 0)
        "mix_peer_node": {"color": "#FFB6C1", "size": 1800}, # ピンク: ピア(R)ノード
        "reagent_node": {"color": "#FFDAB9", "size": 1500},  # オレンジ: 試薬
        "waste_node": {"color": "black", "size": 300, "shape": "o"}, # 黒: 廃棄物
        "default_node": {"color": "gray", "size": 1000},
        "edge": { # 矢印 (エッジ)
            "width": 1.5,
            "arrowsize": 20,
            "connectionstyle": "arc3,rad=0.1",
        },
        "font": { # ラベルのフォント
            "font_size": 10,
            "font_weight": "bold",
            "font_color": "black",
        },
        "edge_label_bbox": dict(facecolor="white", edgecolor="none", alpha=0.7, pad=1),
        "edge_colormap": "viridis", # エッジの色 (量に応じて変わる)
    }
    # --- グラフのレイアウト設定 ---
    LAYOUT_CONFIG = {
        "x_gap": 6.0, # ノード間のX方向の間隔
        "y_gap": 5.0, # ノード間のY方向の間隔 (レベル間)
        "tree_gap": 10.0, # ターゲットツリー間の間隔
        "waste_node_offset_x": 3.5, # 廃棄物ノードのオフセット
        "waste_node_stagger_y": 0.8,
    }

    def __init__(self, problem, model):
        """
        Args:
            problem (MTWMProblem): 問題定義
            model (OrToolsSolutionModel): 解かれたモデル
        """
        self.problem = problem
        self.model = model 

    def visualize_solution(self, output_dir):
        """可視化のメインフロー"""
        
        # 1. 解モデルからグラフ(G)とエッジの流量(edge_volumes)を構築
        graph, edge_volumes = self._build_graph_from_model()
        
        if not graph.nodes():
            print("No active nodes to visualize.")
            return
            
        # 2. グラフ(G)に基づいて各ノードの描画位置(positions)を計算
        positions = self._calculate_node_positions(graph)
        
        # 3. グラフ(G), 位置(positions), 流量(edge_volumes) を使って描画し、保存
        self._draw_graph(graph, positions, edge_volumes, output_dir)

    def _build_graph_from_model(self):
        """
        OrToolsSolutionModel を解析し、
        networkx の DiGraph (有向グラフ) オブジェクトを構築する。
        """
        G = nx.DiGraph()
        edge_volumes = {} # エッジ (矢印) のラベル (流量) を格納

        # 1. アクティブなDFMMノードを処理
        # (解モデルをイテレートし、total_input > 0 のノードのみを抽出)
        for (
            target_idx,
            level,
            node_idx,
            node_vars,  # Or-Tools の 'node_vars'
            total_input,
        ) in self._iterate_active_nodes():
            
            node_name = create_dfmm_node_name(target_idx, level, node_idx)
            ratio_vals = [self.model._v(r) for r in node_vars["ratio_vars"]]

            # ノードのラベル (例: "R1:[2:11:5]" や "[1:5:0]")
            label = (
                f"R{target_idx+1}:[{':'.join(map(str, ratio_vals))}]"
                if level == 0
                else ":".join(map(str, ratio_vals))
            )
            # グラフにノードを追加
            G.add_node(
                node_name, label=label, level=level, target=target_idx, type="mix"
            )

            # このノードから廃棄物が出ていれば、廃棄物ノードも追加
            self._add_waste_node(G, node_vars, node_name)
            
            # このノードに試薬が投入されていれば、試薬ノードとエッジを追加
            self._add_reagent_edges(
                G, edge_volumes, node_vars, node_name, level, target_idx
            )
            
            # このノードに共有(中間液)が投入されていれば、共有エッジを追加
            self._add_sharing_edges(G, edge_volumes, node_vars, node_name, target_idx)

        # 2. アクティブなピア(R)ノードを処理
        for i, peer_node_vars in enumerate(self.model.peer_vars):
            total_input = self.model._v(peer_node_vars["total_input_var"])
            if total_input == 0:
                continue # 使われていないピア(R)ノードはスキップ

            node_name = peer_node_vars["name"]
            ratio_vals = [self.model._v(r) for r in peer_node_vars["ratio_vars"]]
            label = f"R-Mix\n[{':'.join(map(str, ratio_vals))}]"

            # ピア(R)ノードの材料(A, B)の情報を problem から取得
            z3_peer_node = self.problem.peer_nodes[i]
            src_a_id = z3_peer_node["source_a_id"]
            src_b_id = z3_peer_node["source_b_id"]

            # グラフ表示用の実効レベルとターゲットID
            peer_level = (src_a_id[1] + src_b_id[1]) / 2.0 - 0.5
            peer_target_idx = src_a_id[0]

            # グラフにノードを追加
            G.add_node(
                node_name,
                label=label,
                level=peer_level,
                target=peer_target_idx,
                type="mix_peer",
            )

            # 廃棄物ノードを追加
            self._add_waste_node(G, peer_node_vars, node_name)

            # 入力エッジ (A -> ピア, B -> ピア) を追加
            w_a = self.model._v(peer_node_vars["input_vars"]["from_a"])
            w_b = self.model._v(peer_node_vars["input_vars"]["from_b"])

            name_a = create_dfmm_node_name(src_a_id[0], src_a_id[1], src_a_id[2])
            name_b = create_dfmm_node_name(src_b_id[0], src_b_id[1], src_b_id[2])

            if w_a > 0:
                G.add_edge(name_a, node_name, volume=w_a)
                edge_volumes[(name_a, node_name)] = w_a
            if w_b > 0:
                G.add_edge(name_b, node_name, volume=w_b)
                edge_volumes[(name_b, node_name)] = w_b

        return G, edge_volumes

    def _iterate_active_nodes(self):
        """ヘルパー: OrToolsSolutionModel をイテレートし、
           アクティブな (total_input > 0) DFMMノードのみを yield する
        """
        for target_idx, tree_vars in enumerate(self.model.forest_vars):
            for level, node_vars_list in tree_vars.items():
                for node_idx, node_vars in enumerate(node_vars_list):
                    total_input = self.model._v(node_vars["total_input_var"])
                    if total_input > 0:
                        yield target_idx, level, node_idx, node_vars, total_input

    def _add_waste_node(self, G, node_vars, parent_name):
        """ヘルパー: 廃棄物ノードを追加する"""
        waste_var = node_vars.get("waste_var")
        if waste_var is not None and self.model._v(waste_var) > 0:
            waste_node_name = f"waste_{parent_name}"
            G.add_node(
                waste_node_name,
                level=G.nodes[parent_name]["level"],
                target=G.nodes[parent_name]["target"],
                type="waste",
            )
            # 廃棄物ノードは、レイアウト計算用の見えないエッジで親と接続
            G.add_edge(parent_name, waste_node_name, style="invisible")

    def _add_reagent_edges(
        self, G, edge_volumes, node_vars, dest_name, level, target_idx
    ):
        """ヘルパー: 試薬ノードと、そこからのエッジを追加する"""
        for r_idx, r_var in enumerate(node_vars.get("reagent_vars", [])):
            if (r_val := self.model._v(r_var)) > 0:
                reagent_name = f"Reagent_{dest_name}_t{r_idx}" # 試薬ノード名は一意にする
                G.add_node(
                    reagent_name,
                    label=chr(0x2460 + r_idx), # ラベルは ①, ②, ...
                    level=level + 1, # 試薬はノードより 1 レベル下 (グラフの上側) に表示
                    target=target_idx,
                    type="reagent",
                )
                G.add_edge(reagent_name, dest_name, volume=r_val)
                edge_volumes[(reagent_name, dest_name)] = r_val

    def _add_sharing_edges(
        self, G, edge_volumes, node_vars, dest_name, dest_target_idx
    ):
        """ヘルパー: 共有 (中間液) エッジを追加する"""
        all_sharing = {
            **node_vars.get("intra_sharing_vars", {}),
            **node_vars.get("inter_sharing_vars", {}),
        }
        for key, w_var in all_sharing.items():
            if (val := self.model._v(w_var)) > 0:
                # 共有キー (例: "from_t1_l1_k0") から
                # 供給元(src)のノード名 (例: "mixer_t1_l1_k0") を特定
                src_name = self._parse_source_node_name(key, dest_target_idx)
                G.add_edge(src_name, dest_name, volume=val)
                edge_volumes[(src_name, dest_name)] = val

    def _parse_source_node_name(self, key, dest_target_idx):
        """ヘルパー: 共有キー文字列 ("from_...") から供給元ノード名を逆引きする"""
        key_no_prefix = key.replace("from_", "")
        try:
            parsed_key = parse_sharing_key(key_no_prefix) # utils/helpers の関数
            if parsed_key["type"] == "PEER":
                idx = parsed_key["idx"]
                return self.problem.peer_nodes[idx]["name"]
            elif parsed_key["type"] == "DFMM":
                return create_dfmm_node_name(
                    parsed_key["target_idx"],
                    parsed_key["level"],
                    parsed_key["node_idx"],
                )
            elif parsed_key["type"] == "INTRA":
                # ツリー内(Intra)共有の場合、ターゲットIDは供給先(dest)と同じ
                return create_dfmm_node_name(
                    dest_target_idx,
                    parsed_key["level"],
                    parsed_key["node_idx"],
                )
        except (IndexError, KeyError, ValueError):
            return f"Invalid_Node_Key_{key}"

    def _calculate_node_positions(self, G):
        """
        matplotlib で描画するための、各ノードの (x, y) 座標を計算する。
        ターゲットツリーごとに横に並べ、レベルごとに縦に並べるレイアウト。
        """
        pos = {}
        # グラフに存在するターゲットID (0, 1, 2...) をソート
        targets = sorted(
            {d["target"] for n, d in G.nodes(data=True) if d.get("target") is not None}
        )
        current_x_offset = 0.0

        # ターゲットツリーごとに処理
        for target_idx in targets:
            # このターゲットに属するノード (廃棄物以外) を抽出
            sub_nodes = [
                n
                for n, d in G.nodes(data=True)
                if d.get("target") == target_idx and d.get("type") != "waste"
            ]
            if not sub_nodes:
                continue
                
            # このツリーのノード位置を計算 (レベルごと)
            max_width = self._position_nodes_by_level(
                G, pos, sub_nodes, current_x_offset
            )
            
            # このツリーの廃棄物ノードの位置を計算
            self._position_waste_nodes(G, pos, target_idx)
            
            # 次のツリーの X 座標オフセットを更新
            current_x_offset += max_width + self.LAYOUT_CONFIG["tree_gap"]
            
        return pos

    def _position_nodes_by_level(self, G, pos, sub_nodes, x_offset):
        """ヘルパー: ターゲットツリー内のノード位置をレベルごとに計算"""
        max_width_in_tree = 0
        levels = sorted({G.nodes[n]["level"] for n in sub_nodes})

        for level in levels:
            # このレベルのノード (例: [mixer_t0_l1_k0, mixer_t0_l1_k1])
            nodes_at_level = [n for n in sub_nodes if G.nodes[n].get("level") == level]
            
            # このレベルのノードに接続されている「試薬ノード」も取得
            reagent_nodes = {
                u
                for n in nodes_at_level
                for u, _ in G.in_edges(n)
                if G.nodes.get(u, {}).get("type") == "reagent"
            }
            
            # レベルノード + 試薬ノード を合わせて1つの行(row)として扱う
            full_row = sorted(list(set(nodes_at_level) | reagent_nodes))
            
            # 行全体の幅を計算し、中央揃えにするための開始X座標を計算
            total_width = (len(full_row) - 1) * self.LAYOUT_CONFIG["x_gap"]
            start_x = x_offset - total_width / 2.0

            # 各ノードの (x, y) 座標を決定
            for i, node_name in enumerate(full_row):
                pos[node_name] = (
                    start_x + i * self.LAYOUT_CONFIG["x_gap"], # X座標
                    -level * self.LAYOUT_CONFIG["y_gap"],     # Y座標 (レベルが低いほど Y が 0 に近い)
                )
            max_width_in_tree = max(max_width_in_tree, total_width)
        return max_width_in_tree

    def _position_waste_nodes(self, G, pos, target_idx):
        """ヘルパー: 廃棄物ノードの位置を計算 (親ノードの右横)"""
        waste_nodes = [
            n
            for n, d in G.nodes(data=True)
            if d.get("type") == "waste" and d.get("target") == target_idx
        ]
        for wn in waste_nodes:
            parent = next(iter(G.predecessors(wn)), None) # 親ノードを取得
            if parent and parent in pos:
                px, py = pos[parent] # 親の (x, y)
                # 親の (x + offset, y)
                pos[wn] = (px + self.LAYOUT_CONFIG["waste_node_offset_x"], py)

    def _draw_graph(self, G, pos, edge_volumes, output_dir):
        """
        matplotlib を使って、計算された位置(pos)にグラフ(G)を描画し、
        PNGファイルとして保存する。
        """
        fig, ax = plt.subplots(figsize=(20, 12)) # 描画領域を作成
        
        # 描画対象のノードとエッジをフィルタリング
        drawable_nodes = [n for n in G.nodes() if n in pos]
        drawable_edges = [
            (u, v)
            for u, v, d in G.edges(data=True)
            if d.get("style") != "invisible" and u in pos and v in pos # 見えないエッジは除外
        ]
        
        # --- 1. ノードの描画 ---
        node_styles = {n: self._get_node_style(G.nodes[n]) for n in drawable_nodes}
        # ノードの形状 (shape) ごとに分けて描画 (例: 'o' と 's' が混在する場合)
        for shape in {s["shape"] for s in node_styles.values()}:
            nodelist = [n for n, s in node_styles.items() if s["shape"] == shape]
            nx.draw_networkx_nodes(
                G,
                pos,
                ax=ax,
                nodelist=nodelist,
                node_shape=shape,
                node_size=[node_styles[n]["size"] for n in nodelist],
                node_color=[node_styles[n]["color"] for n in nodelist],
                edgecolors="black",
                linewidths=1.0,
            )
            
        # --- 2. ノードラベル (文字) の描画 ---
        labels = {
            n: d["label"]
            for n, d in G.nodes(data=True)
            if n in drawable_nodes and "label" in d and d.get("type") != "waste"
        }
        nx.draw_networkx_labels(
            G, pos, ax=ax, labels=labels, **self.STYLE_CONFIG["font"]
        )
        
        # --- 3. エッジ (矢印) の描画 ---
        if edge_volumes:
            volumes = [edge_volumes[edge] for edge in drawable_edges]
            if volumes:
                # 流量 (volume) に応じてエッジの色を変える (カラーマップ)
                min_vol = min(volumes)
                max_vol = max(volumes)
                norm = mcolors.Normalize(vmin=min_vol, vmax=max_vol)
                cmap = plt.get_cmap(self.STYLE_CONFIG["edge_colormap"])
                edge_colors = [
                    cmap(norm(edge_volumes[edge])) for edge in drawable_edges
                ]
            else:
                edge_colors = ["gray"] * len(drawable_edges)
        else:
            edge_colors = ["gray"] * len(drawable_edges)
            
        nx.draw_networkx_edges(
            G,
            pos,
            edgelist=drawable_edges,
            ax=ax,
            node_size=self.STYLE_CONFIG["mix_node"]["size"],
            edge_color=edge_colors,
            **self.STYLE_CONFIG["edge"],
        )
        
        # --- 4. エッジラベル (流量の数値) の描画 ---
        # [MODIFIED] エッジのラベル（数字）を表示しないようにコメントアウト
        # edge_labels = {k: v for k, v in edge_volumes.items() if k in drawable_edges}
        # nx.draw_networkx_edge_labels(
        #     G,
        #     pos,
        #     edge_labels=edge_labels,
        #     font_size=self.STYLE_CONFIG["font"]["font_size"],
        #     font_color=self.STYLE_CONFIG["font"]["font_color"],
        #     bbox=self.STYLE_CONFIG["edge_label_bbox"],
        # )
        
        # --- 5. カラーバー (凡例) の描画 ---
        if edge_volumes and volumes:
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])
            cbar = fig.colorbar(
                sm, ax=ax, orientation="vertical", fraction=0.02, pad=0.04
            )
            cbar.set_label("Volume", rotation=270, labelpad=15, fontsize=12)
            
        # --- 6. 保存 ---
        ax.set_title("Mixing Tree Visualization", fontsize=18, pad=20)
        ax.axis("off") # 軸を非表示
        plt.tight_layout()
        image_path = os.path.join(output_dir, "mixing_tree_visualization.png")
        try:
            plt.savefig(image_path, dpi=300, bbox_inches="tight")
            print(f"Graph visualization saved to: {image_path}")
        except Exception as e:
            print(f"Error saving visualization image: {e}")
        finally:
            plt.close(fig) # メモリを解放

    def _get_node_style(self, node_data):
        """ヘルパー: ノードのデータ (type, level) に応じてスタイル設定を返す"""
        cfg = self.STYLE_CONFIG
        node_type = node_data.get("type")
        if node_type == "mix":
            style = (
                cfg["target_node"] if node_data.get("level") == 0 else cfg["mix_node"]
            )
        elif node_type == "mix_peer":
            style = cfg["mix_peer_node"]
        elif node_type == "reagent":
            style = cfg["reagent_node"]
        elif node_type == "waste":
            style = cfg["waste_node"]
        else:
            style = cfg["default_node"]
        return {
            "color": style["color"],
            "size": style["size"],
            "shape": style.get("shape", "o"), # デフォルトは 'o' (円)
        }