"""
開発用: ローカル DB に管理ユーザーを作成する簡易スクリプト。

使い方:
    python scripts/create_local_admin.py

環境: FLASK_ENV=development で実行してください。
"""
from getpass import getpass
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User  # models の場所を適宜修正してください

def main():
    app = create_app("development")
    with app.app_context():
        username = input("admin username [localadmin]: ") or "localadmin"
        pwd = getpass("password [password]: ") or "password"
        u = db.session.query(User).filter_by(username=username).first()
        if u:
            print("ユーザーは既に存在します:", username)
            return
        user = User(username=username, password_hash=generate_password_hash(pwd))
        if hasattr(user, "is_admin"):
            user.is_admin = True
        db.session.add(user)
        db.session.commit()
        print("作成しました:", username)
        print("DB:", getattr(db.engine.url, "database", None))

if __name__ == "__main__":
    main()