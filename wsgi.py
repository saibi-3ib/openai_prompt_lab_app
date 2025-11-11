# wsgi.py — Gunicorn 用エントリポイント
# 単に run.py に定義した Flask アプリをエクスポートします。

from run import app

# If you want a WSGI callable named "application" instead, uncomment:
# application = app