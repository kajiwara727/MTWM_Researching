import os
import glob
import json
import pandas as pd
from collections import defaultdict

def load_run_data_from_json(json_path):
    """
    JSONファイルから実行結果を読み込み、辞書形式で返します。
    Key: run_name, Value: data dict
    """
    run_data = {}
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
            
        for entry in data_list:
            # 必要なフィールドが揃っているか確認
            if entry.get('final_value') is not None:
                run_name = entry['run_name']
                run_data[run_name] = {
                    'waste': entry.get('total_waste', 0),
                    'reagents': entry.get('total_reagents', 0),
                    'ops': entry.get('total_operations', 0)
                }
    except Exception as e:
        print(f"エラー: JSONファイル '{json_path}' の読み込みに失敗しました: {e}")
        return None
        
    return run_data

def print_ops_analysis(data_pairs, sort_reverse=True):
    """操作数分析を表示するヘルパー関数"""
    if not data_pairs:
        print("   該当するケースはありません。")
        return

    # (廃棄削減量, 試薬削減量) でソート
    sorted_pairs = sorted(data_pairs.items(), key=lambda x: x[0], reverse=sort_reverse)
    
    for (w_red, r_red), ops_red_list in sorted_pairs:
        w_text = f"{w_red:.1f}減" if w_red > 0 else (f"{abs(w_red):.1f}増" if w_red < 0 else "維持(±0)")
        r_text = f"{r_red}減" if r_red > 0 else (f"{abs(r_red)}増" if r_red < 0 else "維持(±0)")
        
        print(f"\n[ケース] 廃棄: {w_text}, 試薬: {r_text} (合計 {len(ops_red_list)} 件)")
        
        ops_counts = defaultdict(int)
        for op_red in ops_red_list:
            ops_counts[op_red] += 1
        
        for op_red, count in sorted(ops_counts.items(), key=lambda x: x[0], reverse=True):
            if op_red > 0:
                print(f"   - 操作数 {op_red} 削減: {count} 件")
            elif op_red < 0:
                print(f"   - 操作数 {abs(op_red)} 増加: {count} 件")
            else:
                print(f"   - 操作数 維持 (±0): {count} 件")

# --- メイン処理 ---

# 1. 比較対象ファイルの検索 (JSONを優先)
# 従来手法 (Previous) は固定と仮定、あるいは引数化も可能
previous_file_json = "previous_results.json" 
# ※もし従来手法のJSONがない場合は、テキスト解析版を残すか、一度実行してJSONを作る必要があります。
# ここでは「両方JSONがある」前提、もしくは「提案手法はJSON、従来はテキスト」のハイブリッドも検討できますが、
# シンプル化のため「提案手法のJSON」を探すロジックを実装します。

search_pattern = "*_results.json" # JSONを探す
print(f"パターン '{search_pattern}' で提案手法(Proposed)のファイルを検索します...")
json_files = glob.glob(search_pattern)

if not json_files:
    print("エラー: JSON形式の結果ファイルが見つかりません。")
    print("Runnerを実行して 'results.json' を生成してください。")
    import sys; sys.exit()

proposed_file = json_files[0]
if len(json_files) > 1:
    print("複数のファイルが見つかりました:")
    for i, f in enumerate(json_files):
        print(f"   [{i+1}] {f}")
    idx = int(input("番号を選択: ")) - 1
    proposed_file = json_files[idx]

print(f"\nProposed File (JSON): {proposed_file}")

# 2. データの読み込み
proposed_data = load_run_data_from_json(proposed_file)

# ★注意: 従来手法のデータ(previous_data)について
# もし従来手法のJSONがない場合、過去のテキスト解析ロジックで読み込む必要があります。
# ここでは「比較用JSON」が存在すると仮定、または「今回は解析ロジックの刷新」として
# JSON同士の比較コードを示します。
# (必要であれば、テキストパーサー関数 `parse_summary_file` をここに復活させてください)

# ダミー/テスト用: 比較対象がない場合、単体分析モードとして動作させるなどの分岐も可能
if proposed_data is None:
    import sys; sys.exit()

# もし previous_results.json がなければ、とりあえず入力を促す
previous_file = "previous_results.json"
if not os.path.exists(previous_file):
    print(f"\n警告: 比較対象 '{previous_file}' が見つかりません。")
    print("比較を行うには、従来手法の結果もJSONとして保存してください。")
    # 処理中断または単体表示へ
else:
    previous_data = load_run_data_from_json(previous_file)
    
    # 3. 比較ロジック (共通ランのみ)
    common_runs = sorted(list(set(previous_data.keys()) & set(proposed_data.keys())))
    print(f"\n合計 {len(common_runs)} 件の共通ランを比較します。")

    ops_analysis_positive = defaultdict(list)
    ops_analysis_negative = defaultdict(list)
    comparison_results = []

    for run_name in common_runs:
        prev = previous_data[run_name]
        prop = proposed_data[run_name]

        waste_red = prev['waste'] - prop['waste']
        reag_red = prev['reagents'] - prop['reagents']
        ops_red = prev['ops'] - prop['ops']

        # 勝敗判定
        w_win = "WIN" if prop['waste'] < prev['waste'] else ("LOSE" if prop['waste'] > prev['waste'] else "DRAW")
        r_win = "WIN" if prop['reagents'] < prev['reagents'] else ("LOSE" if prop['reagents'] > prev['reagents'] else "DRAW")

        # 分析用データ蓄積
        if waste_red > 0:
            ops_analysis_positive[(waste_red, reag_red)].append(ops_red)
        else:
            ops_analysis_negative[(waste_red, reag_red)].append(ops_red)

        comparison_results.append({
            'Run Name': run_name,
            'Waste Result': w_win, 'Waste Reduction': waste_red,
            'Reagent Result': r_win, 'Reagent Reduction': reag_red,
            'Ops Reduction': ops_red,
            'Prop Waste': prop['waste'], 'Prev Waste': prev['waste'],
            'Prop Ops': prop['ops'], 'Prev Ops': prev['ops']
        })

    # 4. 結果表示
    print("\n--- 廃棄削減 ( > 0 ) のケース ---")
    print_ops_analysis(ops_analysis_positive, sort_reverse=True)

    print("\n--- 廃棄維持・増加 ( <= 0 ) のケース ---")
    print_ops_analysis(ops_analysis_negative, sort_reverse=False)

    # 5. CSV保存
    df = pd.DataFrame(comparison_results)
    if not df.empty:
        os.makedirs("CSV_Result", exist_ok=True)
        csv_path = os.path.join("CSV_Result", f"{os.path.splitext(os.path.basename(proposed_file))[0]}_comparison.csv")
        df.sort_values(by=['Waste Reduction', 'Reagent Reduction'], ascending=[False, False], inplace=True)
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"\n詳細な比較結果を '{csv_path}' に保存しました。")