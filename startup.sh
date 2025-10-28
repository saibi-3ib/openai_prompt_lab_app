#!/usr/bin/env bash

# Rendder の環境変数が読み込まれていることを確認

# 1. データベースマイグレーションの実行
# alembic がアップグレード履歴のテーブル (alembic_version) をチェックし、
# 必要なマイグレーションのみを実行します。
echo "--- Running Alembic Migrations ---"
alembic upgrade head

# 2. Gunicorn によるアプリケーションの起動
echo "--- Starting Gunicorn ---"
# Gunicorn をワーカー数 3 で起動。app.py の app 変数を参照。
exec gunicorn --workers 3 app:app