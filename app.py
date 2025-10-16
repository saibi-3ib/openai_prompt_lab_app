# render_template_stringの代わりにrender_templateをインポート
from flask import Flask, render_template
from models import SessionLocal, CollectedPost

app = Flask(__name__)

@app.route('/')
def index():
    db = SessionLocal()
    try:
        posts = db.query(CollectedPost).order_by(CollectedPost.id.desc()).limit(50).all()
        # "index.html"ファイルを指定してレンダリングする
        return render_template("index.html", posts=posts)
    finally:
        db.close()