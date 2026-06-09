# MTWM-Solver: 複数ターゲット混合における廃棄物最小化ソルバー 🧪

### 概要

**MTWM (Multi-Target Waste Minimization) Solver**は、複数の目標混合液（Multi-Target）を生成する過程において、試薬の廃棄（Waste）を最小化（Minimization）する最適な手順を導き出すための高度な最適化計算ツールです。

***

### コアコンセプト

このソルバーは、主に2つの強力な理論に基づいています。

#### 1. DFMM (Digital Microfluidic Mixing) アルゴリズム
これは、目標とする混合比率を達成するために、どのような順序で、どのくらいの比率の液体を混ぜ合わせるべきか、という混合ツリーの「設計図」を自動生成するアルゴリズムです。

`core/dfmm.py` に実装されており、比率の合計値を指定された最大混合サイズ（`MAX_MIXER_SIZE`）以下の因数に分解することで、多段階の混合プロセスを数学的に導出します。

#### 2. 制約充足問題 (CSP) ソルバー
CSPソルバーは、複雑な制約条件を満たす解（または最適解）を見つけ出すことに特化した数学的な問題解決エンジンです。

本プロジェクトでは、Googleが開発したオープンソースの**OR-Tools (CP-SAT Solver)**を採用しています。

DFMMで生成された混合ツリーの無数の可能性の中から、「廃棄物量が最小になる」（または操作回数や試薬量が最小になる）という条件を満たす最適な解を探索する役割を担います。

***

### ファイル構成
```
MTWM_Solver_Refactored/
├── main.py                     # アプリケーションのエントリーポイント
├── config.py                   # 最適化の各種設定を行うファイル
├── README.md                   # このファイル
|
├── core/                       # アプリケーションの中核ロジック
│   ├── __init__.py             # coreディレクトリをパッケージとして定義
│   ├── problem.py              # 最適化問題の構造を定義
│   └── dfmm.py                 # DFMMアルゴリズム関連
│   └── or_tools_solver.py      # OR-Toolsソルバーへの制約設定と最適化実行を担当
├
|
├── runners/                    # 実行モードごとの処理フローを管理
│   ├── __init__.py             # runnersパッケージ定義、RUNNER_MAPを保持
│   ├── base_runner.py          # 実行クラスの基底クラス
│   ├── standard_runner.py      # 'auto'/'manual'モード用
│   ├── random_runner.py        # 'random'モード用
│   ├── permutation_runner.py   # 'auto_permutations'モード用
│   └── file_load_runner.py     # 'file_load'モード用
|
├── reporting/                  # 全ての出力・レポート関連機能
│   ├── __init__.py             # reportingディレクトリをパッケージとして定義
│   ├── analyzer.py             # 事前分析レポート
│   ├── reporter.py             # 詳細な結果レポート
│   ├── summary.py              # 複数実行のサマリー
│   └── visualizer.py           # 結果の可視化 (networkx & matplotlib)
|
└── utils/                      # 汎用的な補助機能
    ├── __init__.py             # utilsディレクトリをパッケージとして定義
    ├── config_loader.py        # 設定の読み込み・解釈
    └── helpers.py              # ハッシュ生成、キー生成/解析などのヘルパー関数
```

### 機能詳細

#### 1. 廃棄物・操作回数・試薬量の最適化
`config.py` の `OPTIMIZATION_MODE` で、何を最優先するかを選択できます。
* **`waste`モード**: 生成される総廃棄液量を最小化します。コスト削減や環境負荷低減に直結します。
* **`operations`モード**: 混合操作（DFMMノードとピアRノードの両方）の総回数を最小化します。プロセスの単純化を優先する場合に有効です。
* **`reagents`モード**: 使用される総試薬量を最小化します。試薬コストが主要な場合に有効です。

#### 2. 高度な共有ロジック（中間液の再利用）
異なるターゲット（例：製品Aと製品B）を製造する過程で生成された中間液を、別のターゲット（例：製品C）の製造に利用できないかを自動で探索します。
* **ツリー内共有(Intra-sharing)**: 同じターゲットのツリー内で、上位レベルのノードが下位レベルのノードの中間液を使用します。
* **ツリー間共有(Inter-sharing)**: あるターゲットのツリーのノードが、**別の**ターゲットのツリーの中間液を使用します。
* **ピア(R)ノード共有**: 同じ濃度（P値）を持つ2つの中間液を1:1で混合して新しい中間液（ピアRノード）を生成し、それを他のDFMMノードが使用します。

これにより、従来は廃棄されていた液体を再利用し、全体のコストと廃棄物を削減します。共有の可否は、レベル差（`MAX_LEVEL_DIFF`）やP値の制約に基づいて自動的に判断されます。

#### 3. 包括的なレポートと可視化 📊
最適化が完了すると、実行名に基づいたディレクトリ内に詳細なレポートが出力されます。
* **`summary.txt`**:
    * **最適化設定**: どの `MODE` で、どのような制約（`MAX_MIXER_SIZE` など）で計算したかの記録。
    * **最終結果**: 選択した目的（`waste`など）の最小値、総操作回数、総試薬使用量、総廃棄物量。
    * **混合プロセス詳細**: どのノード（例: `mixer_t0_l1_k0`）で、どの試薬や中間液（例: `peer_mixer_...`）を、どれだけの量混合したか、という具体的な手順がすべて記録されます。
* **`mixing_tree_visualization.png`**:
    * **緑のノード**: 最終ターゲット液。
    * **水色のノード**: DFMM中間生成物。
    * **ピンクのノード**: ピア(R)混合ノード。
    * **オレンジのノード (①, ②..)**: 投入された純粋な試薬。
    * **黒い点**: 廃棄物。
    * **矢印と数字**: 液体の流れと、その移動量。
    * この図を見ることで、複雑な共有関係や混合プロセスを直感的に理解できます。

* **`_pre_run_analysis.txt`**: 最適化実行前に生成される、ツリー構造、P値、共有可能性の分析レポート。
* **複数実行サマリー**: `random`, `permutation`, `file_load` モードでは、全実行結果をまとめたサマリーファイル（例: `_random_runs_summary.txt`）も生成されます。

***

### アーキテクチャと処理フロー ⚙️

本プログラムは、責務分離の原則に基づき、機能ごとにモジュール化されています。

1.  **起動 (`main.py`)**:
    * エントリーポイント。`config.py` の設定を `utils/config_loader.py` 経由で読み込みます。
    * `FACTOR_EXECUTION_MODE` に応じて、`runners/__init__.py` の `RUNNER_MAP` から適切な実行戦略クラス（`StandardRunner` など）を選択し、インスタンス化します。

2.  **実行管理 (`runners/`)**:
    * 選択されたRunner（例: `RandomRunner`）が、シミュレーションのループや設定の生成など、全体の進行を管理します。
    * 個々の最適化タスクは、共通の `_run_single_optimization` メソッド（`base_runner.py` 内）に渡されます。

3.  **問題構築 (`core/`)**:
    * `_run_single_optimization` 内では、まず `core/dfmm.py` がターゲット設定から混合ツリーの構造とP値を計算します。
    * 次に `core/problem.py` が、その構造に基づいて、ソルバーが扱う変数（液量、比率など）や共有可能性、ピア(R)ノードなどを定義します。

4.  **最適化 (`or_tools_solver.py`)**:
    * `core/problem` で定義された問題オブジェクトを受け取り、すべての制約（流量保存則、濃度保存則、ミキサー容量、物理的制約など）をOR-Tools CP-SATモデルに追加します。
    * `solver.Solve()` を呼び出し、目的変数（総廃棄物量など）を最小化する解の探索を開始します。

5.  **出力 (`reporting/`)**:
    * OR-Toolsソルバーが解を見つけると、`or_tools_solver.py` 内の `OrToolsSolutionModel` がその解を解析可能な形式にまとめます。
    * `reporting/reporter.py` が `OrToolsSolutionModel` から結果を受け取り、人間が読める形式のサマリー（`summary.txt`）を生成します。
    * 同時に `reporting/visualizer.py` が解データから混合フローのグラフを構築し、画像（`.png`）として保存します。

***

### 使い方ガイド：初めての最適化チュートリアル 🚀

このガイドでは、`manual`モードを使用して、特定のターゲット混合液の製造プロセスをゼロから最適化する手順を解説します。

---

#### ステップ1：環境のセットアップ

まず、プログラムを実行するための準備をします。

1.  **仮想環境の作成と有効化**:
    ターミナルを開き、プロジェクトフォルダに移動して実行します。
    ```bash
    python -m venv .venv
    # Windows: .\.venv\Scripts\activate
    # Mac/Linux: source .venv/bin/activate
    ```

2.  **依存ライブラリのインストール**:
    有効化した仮想環境で、以下のコマンドを実行します。
    ```bash
    pip install ortools networkx matplotlib
    ```

---

#### ステップ2：最適化シナリオの設定 (`config.py`)

次に、`config.py` ファイルを開き、どのような最適化を行いたいかを定義します。今回は、2種類のターゲット混合液（製品A, 製品B）の製造を想定します。

1.  **実行名の設定**:
    今回の実行結果が保存されるフォルダ名を決めます。
    ```python
    RUN_NAME = "My_First_Optimization"
    ```

2.  **実行モードの選択**:
    今回は、混合の階層（`factors`）を我々が直接指定する `manual` モードを使用します。
    ```python
    FACTOR_EXECUTION_MODE = "manual"
    ```
    * `auto`モード: `factors` を自動計算させたい場合。
    * `random`モード: ランダムな `ratios` で多数のシミュレーションを行いたい場合。
    * `auto_permutations`モード: `auto` で計算された `factors` の全順列を試し、最適な階層構造を探したい場合。
    * `file_load`モード: JSONファイルから設定を読み込む場合。

3.  **ターゲットの定義**:
    `TARGETS_FOR_MANUAL_MODE` のセクションを編集し、製造したい製品の仕様を定義します。
    ```python
    # --- 'manual' モード用設定 ---
    TARGETS_FOR_MANUAL_MODE = [
        # 製品A: 試薬1,2,3を [2:11:5] の比率で混合。合計18。
        # 混合階層(factors)は [3, 2, 3] とする (3*2*3 = 18)。
        {'name': 'Product_A', 'ratios': [2, 11, 5], 'factors': [3, 2, 3]},

        # 製品B: 試薬1,2,3を [12:5:1] の比率で混合。合計18。
        # 混合階層(factors)は製品Aと同じ [3, 2, 3] を試す。
        {'name': 'Product_B', 'ratios': [12, 5, 1], 'factors': [3, 2, 3]},
    ]
    ```
    > **💡 `factors`とは？**
    > `ratios` の合計値（この例では18）を構成する因数です。これはDFMMアルゴリズムにおける混合の分割比（各レベルでのミキサーサイズ）を定義し、混合ツリーの構造を決定します。`[3, 2, 3]` は、3段階の混合プロセスを意味します。`factors` の積は `ratios` の合計値と一致する必要があります。また、各 factor は `MAX_MIXER_SIZE` 以下である必要があります。

---

#### ステップ3：最適化の実行

設定が完了したら、ターミナルで `main.py` を実行します。
```bash
python main.py
```
実行が始まると、ターミナルには以下のような進捗が表示されます。

```
設定内容の確認

事前分析レポートの保存先

OR-Toolsソルバーによる最適化の開始・終了メッセージ

--- Factor Determination Mode: MANUAL ---

--- Configuration for this run ---
Run Name: My_First_Optimization
  - Product_A: Ratios = [2, 11, 5], Factors = [3, 2, 3]
  - Product_B: Ratios = [12, 5, 1], Factors = [3, 2, 3]
Optimization Mode: WASTE
-----------------------------------

All outputs for this run will be saved to: 'My_First_Optimization_xxxx/'
Pre-run analysis report saved to: My_First_Optimization_xxxx/_pre_run_analysis.txt

--- Solving the optimization problem (mode: WASTE) with Or-Tools CP-SAT ---
Or-Tools found an optimal solution with waste: 2
--- Or-Tools Solver Finished ---
... (レポート保存メッセージ) ...
ステップ4：結果の分析と解釈
計算が完了すると、My_First_Optimization_xxxx という名前のディレクトリが生成されます。この中の主要なファイルを見ていきましょう。

mixing_tree_visualization.png (可視化レポート) まず、この画像を開いて全体像を把握します。

オレンジ (①, ②, ...): 外部からの試薬。

水色: DFMM中間液。

ピンク: ピア(R)混合液。

緑: 最終ターゲット液。

矢印と数字: 液体の流れと量。

黒い点: 廃棄物。

summary.txt (詳細テキストレポート) 次に、テキストレポートで具体的な数値を確認します。

サマリーセクション:

========================================
Optimization Results for: My_First_Optimization_xxxx
========================================

Solved in 1.23 seconds.

--- Target Configuration ---
Target 1:
  Ratios: 2 : 11 : 5
  Factors: [3, 2, 3]
Target 2:
  Ratios: 12 : 5 : 1
  Factors: [3, 2, 3]

--- Optimization Settings ---
...
----------------------------

Minimum Total Waste: 2
Total mixing operations: 7
Total reagent units used: 38
ここで、総廃棄物が2ユニットで、合計7回の混合操作が必要だったことが分かります。

混合プロセス詳細セクション:

--- Mixing Process Details ---

[Target 1 (Product_A)]
 Level 1.0:
   Node mixer_t0_l1_k0: total_input = 6
     Ratio composition: [1, 5, 0]
     Mixing: 1 x Reagent1 + 5 x Reagent2
 Level 0.0:
   Node mixer_t0_l0_k0: total_input = 18
     Ratio composition: [2, 11, 5]
     Mixing: 1 x Reagent1 + 1 x Reagent3 + 1 x mixer_t1_l1_k0 + 5 x mixer_t0_l1_k0
... (Target 2 や ピア(R)ノードの詳細も続く) ...
このセクションは、可視化レポートの各ノードが「何でできているか」を示しています。

ノード命名規則: mixer_t{ターゲット番号}_l{階層レベル}_k{ノードインデックス}

mixer_t0_l1_k0: ターゲット0番（Product_A）の、階層1（中間層）にある、0番目のノード。

解釈:

mixer_t0_l1_k0 は、試薬1を1ユニット、試薬2を5ユニット混ぜて作られています。

最終製品である mixer_t0_l0_k0（Product_A）は、試薬1と3、自身の中間液 mixer_t0_l1_k0 だけでなく、ターゲット2の中間液である mixer_t1_l1_k0 も利用（ツリー間共有）して作られていることが分かります。
```
