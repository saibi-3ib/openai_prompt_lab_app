from pathlib import Path
import sys

# プロジェクトルートを sys.path に追加（CI から直接実行しても app を import できるようにする）
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.extensions import db

def main():
    app = create_app("development")
    with app.app_context():
        # テーブルがなければ作る（既にあれば何もしない）
        db.create_all()
    print("create_all complete")

if __name__ == "__main__":
    main()