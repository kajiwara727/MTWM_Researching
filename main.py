# runners パッケージから RUNNER_MAP をインポート
# RUNNER_MAP は、実行モード名(str)と、それに対応するRunnerクラス(class)を紐付ける辞書
from runners import RUNNER_MAP 

# utils.config_loader モジュールから Config クラスをインポート
# Config クラスは、config.py の設定値を保持している
from utils import Config


def main():
    """
    アプリケーションのエントリーポイント（プログラムの開始地点）。
    
    1. config.py の MODE の値 (FACTOR_EXECUTION_MODE) を Config クラス経由で読み込む。
    2. RUNNER_MAPから、そのモードに対応する適切な実行戦略（ランナー）クラスを選択する。
    3. 選択したランナークラスをインスタンス化し、実行(.run())する。
    """
    
    # 1. Configクラスから現在設定されている実行モードを取得
    mode = Config.MODE
    print(f"--- Factor Determination Mode: {mode.upper()} ---")

    # 2. RUNNER_MAP (辞書) から、モード名(mode)をキーにして、
    #    対応するRunnerクラス (例: StandardRunner, RandomRunnerなど) を取得
    #    .get(mode) は、キーが存在しない場合に None を返す
    runner_class = RUNNER_MAP.get(mode)

    # 3. 実行
    if runner_class:
        # もし対応するクラスが見つかった場合 (runner_class が None でない)
        
        # Config クラス全体を引数として渡し、ランナークラスをインスタンス化
        # (例: runner = StandardRunner(Config))
        runner = runner_class(Config)
        
        # インスタンス化されたランナーの run() メソッドを呼び出し、処理を開始
        runner.run()
    else:
        # もし config.py のモード名が RUNNER_MAP に存在しなかった場合
        # エラーメッセージを表示してプログラムを終了
        raise ValueError(f"Unknown FACTOR_EXECUTION_MODE: '{mode}'.")


if __name__ == "__main__":
    """
    このスクリプトが直接実行された場合 (例: `python main.py`) に、
    main() 関数を呼び出す。
    
    (他のファイルから `import main` されても main() は自動実行されない)
    """
    main()