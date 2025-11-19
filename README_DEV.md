# 開発メモ (local)

このプロジェクトをローカルで素早く立ち上げるための手順をまとめます。

1. 仮想環境と依存関係
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. 環境変数（開発用）
```bash
export FLASK_ENV=development
export DISABLE_FORCE_HTTPS=1   # 開発中は HTTPS リダイレクトを無効化
```

3. マイグレーションの適用（初回）
```bash
flask db upgrade
```
マイグレーションはデフォルトで `instance/dev.db` に適用されます。DB の場所を変えたい場合は `DATABASE_URL` を明示してください。

4. テスト用管理ユーザー作成（任意）
```bash
python scripts/create_local_admin.py
# or
python - <<'PY'
from app import create_app
from app.extensions import db
from app.models import User
from werkzeug.security import generate_password_hash
app = create_app('development')
with app.app_context():
    u = User(username='localadmin', password_hash=generate_password_hash('password'))
    if hasattr(u, 'is_admin'):
        u.is_admin = True
    db.session.add(u)
    db.session.commit()
PY
```

5. サーバ起動
```bash
flask run --port 5001
# または
python run.py
```

6. よくある問題
- ブラウザが自動で https へリダイレクトする場合はシークレットモードで試すか、`DISABLE_FORCE_HTTPS=1` を設定してください。
- DB が空に見える場合は `instance/dev.db` を確認してください。
