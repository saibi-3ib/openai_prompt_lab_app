import os
import sys
# プロジェクトルートパスの動的な設定をmodels.pyが依存しているため、
# ここでも sys.path の設定が必要です。

# models.py が依存する環境変数読み込みのための設定
from dotenv import load_dotenv

# models.py が依存するパス解決ロジックをここで再現
# models.py と同じディレクトリ構造を仮定して、プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) 

# models.py のインポートは、パス設定の後に実行
from models import SessionLocal, CollectedPost
from datetime import datetime, timezone
# models.py は内部で load_dotenv() を実行しているため、ここでは不要（念のため残しています）
load_dotenv() 

# --- ▼▼▼ ここでテストデータを編集できます ▼▼▼ ---

# （必須）非常に長い本文
LONG_TEXT = """これは非常に長いテスト投稿です。
1行目。
2行目。
3行目。Autolinker がURL（例: https://google.com）を正しくリンク化するかもテストします。
4行目。このテキストは '...もっと見る' ボタンが表示されるのに十分な長さである必要があります。
5行目。
6行目。
7行目。
8行目。
9行目。
10行目。これでテストは完了です。"""

# （必須）テスト用の投稿者名
TEST_USERNAME = "LongTextTester"

# （必須）他と重複しないユニークな投稿ID (毎回変更が必要)
TEST_POST_ID = "test_long_post_002" # 001 が既に試行済みであれば 002 に変更してください

# （必須）適当なURL
TEST_SOURCE_URL = "https://example.com/post/002"

# --- ▲▲▲ 編集はここまで ▲▲▲ ---


def insert_post():
    db = SessionLocal()
    
    # models.py 内で定義した接続先を表示
    db_name = os.environ.get('DB_FILENAME', 'app.db')
    print(f"--- データベース ({db_name}) に接続しました ---")
    
    try:
        existing = db.query(CollectedPost).filter(CollectedPost.post_id == TEST_POST_ID).first()
        if existing:
            print(f"エラー: 投稿ID '{TEST_POST_ID}' は既に存在します。TEST_POST_ID を変更してください。")
            return

        new_post = CollectedPost(
            username = TEST_USERNAME,
            post_id = TEST_POST_ID,
            original_text = LONG_TEXT,
            source_url = TEST_SOURCE_URL,
            posted_at = datetime.now(timezone.utc),
            like_count = 123,
            retweet_count = 45
        )
        
        db.add(new_post)
        
        # 挿入前に明示的に flush/commit の結果を出力
        db.flush() 
        print(f"--- 成功！ ---")
        
        db.commit()
        
        print(f"ユーザー '{TEST_USERNAME}' の長文投稿 (ID: {TEST_POST_ID}) を追加しました。")

    except Exception as e:
        db.rollback() 
        print(f"--- エラーが発生しました ---")
        print(f"詳細: {e}")
    finally:
        db.close()
        print("--- データベース接続を閉じました ---")

if __name__ == "__main__":
    insert_post()