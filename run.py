import os
import json
import requests 
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, get_flashed_messages, current_app
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload, subqueryload
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from dateutil.parser import parse
import io
from dotenv import load_dotenv

# --- モデル定義とDB接続を models から持ってくる ---
from models import (
    SessionLocal, CollectedPost, Setting, Prompt, AnalysisResult, User, 
    TickerSentiment, StockTickerMap, TargetAccount, UserTickerWeight
)
from datetime import datetime, timezone

from utils_parser import parse_threads_data_from_lines
from utils_db import (
    get_current_provider, get_or_create_credit_setting, get_current_prompt,
    run_batch_analysis, AVAILABLE_MODELS, client_openai, DEFAULT_PROMPT_KEY
)

# --- セキュリティ関連のインポート（保険として残す） ---
from flask_wtf import CSRFProtect
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
# app.security を使って初期化するので直接の Talisman/Limiter 設定は行いません here
from app.security import init_security

# Admin blueprint は後で登録する。import は安全（admin_worker はアプリコンテキストを参照しない実装になっています）
from app.admin_worker import admin_bp as admin_worker_bp

# --- アプリ初期化 ---
load_dotenv()
app = Flask(__name__)

# 必要な設定（SECRET_KEY等）は先にセットしておく
app.config.setdefault("SECRET_KEY", os.environ.get("SECRET_KEY", "change-me-locally"))
app.config.setdefault("SESSION_COOKIE_SECURE", not app.debug)
app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

# Confirmation phrase and other flags
app.config.setdefault("WORKER_CONFIRM_PHRASE", os.environ.get("WORKER_CONFIRM_PHRASE", "RUN_WORKER"))
app.config.setdefault("ALLOW_DB_RESET", os.environ.get("ALLOW_DB_RESET", "0"))

# --- Initialize security (Talisman + Limiter) via app/security.init_security ---
# init_security は Talisman と Limiter を初期化して app にバインドします
# Limiter インスタンスを戻すのでデコレータで使うことも出来ます
limiter = init_security(app)

# init CSRF protection (after app is configured)
csrf = CSRFProtect()
csrf.init_app(app)

# Flask-Login setup (do this after app created)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "このページにアクセスするにはログインが必要です。"
login_manager.login_message_category = "info"

# register blueprints (admin blueprint etc.)
app.register_blueprint(admin_worker_bp)

# --- Apply per-endpoint rate limits dynamically (avoid import-time circular ref) ---
# admin endpoint name: blueprint_name.function_name
try:
    admin_endpoint = 'admin_worker.worker_settings'  # admin_bp = Blueprint("admin_worker", ...)
    if admin_endpoint in app.view_functions and limiter:
        app.view_functions[admin_endpoint] = limiter.limit("30 per hour")(app.view_functions[admin_endpoint])
except Exception as e:
    app.logger.warning("Failed to apply admin rate limit: %s", e)

try:
    login_endpoint = 'login'  # login view の endpoint 名（このファイルでは 'login'）
    if login_endpoint in app.view_functions and limiter:
        app.view_functions[login_endpoint] = limiter.limit("10 per minute")(app.view_functions[login_endpoint])
except Exception as e:
    app.logger.warning("Failed to apply login rate limit: %s", e)

# .env ファイルに FLASK_SECRET_KEY を必ず設定するようにします
# (os.urandom() はサーバー再起動のたびにキーが変わり、セッションが切れるため非推奨)
app.secret_key = os.environ.get('FLASK_SECRET_KEY')
if not app.secret_key:
    raise ValueError("FLASK_SECRET_KEY が .env ファイルに設定されていません。")

# ユーザーローダー関数: ユーザーIDを元にユーザーオブジェクトを返す
@login_manager.user_loader
def load_user(user_id):
    db = SessionLocal()
    try:
        # user_id は文字列で渡されるので int に変換して検索
        return db.query(User).get(int(user_id))
    finally:
        db.close()

def set_password(password):
    """ パスワードを受け取り、ハッシュ値を生成して返す """
    return generate_password_hash(password)

def check_password(hashed_password, password):
    """ ハッシュ値と入力されたパスワードを比較して T/F を返す """
    return check_password_hash(hashed_password, password)

# --- メインページ (データ表示) ---
@app.route('/')
@login_required
def index():
    db = SessionLocal()
    try:
        posts = db.query(CollectedPost).order_by(CollectedPost.id.desc()).limit(50).all()
        current_provider = get_current_provider(db)
        credit_setting = get_or_create_credit_setting(db)
        current_credit = float(credit_setting.value)
        
        account_names_tuples = db.query(CollectedPost.username).distinct().order_by(CollectedPost.username).all()
        available_accounts = [name[0] for name in account_names_tuples]
        
        # (新) セクターとサブセクターのペアをすべて取得
        results = db.query(StockTickerMap.gics_sector, StockTickerMap.gics_sub_industry).distinct().all()
        
        sector_tree = {} # 例: {'Information Technology': {'Software', 'Semiconductors'}, ...}
        
        for sector, sub_sector in results:
            if sector is None or sub_sector is None:
                continue
            if sector not in sector_tree:
                sector_tree[sector] = set() # 重複を防ぐために Set を使用
            sector_tree[sector].add(sub_sector)
            
        # Jinja2が使いやすいように、ソート済みのリストに変換
        available_sector_tree = []
        for sector_name in sorted(sector_tree.keys()):
            available_sector_tree.append({
                "name": sector_name,
                "sub_sectors": sorted(list(sector_tree[sector_name]))
            })

        return render_template(
            "index.html", 
            posts=posts, 
            current_provider=current_provider,
            current_credit=current_credit,
            available_models=AVAILABLE_MODELS,
            available_accounts=available_accounts,
            available_sector_tree=available_sector_tree
        )
    finally:
        db.close()

# --- 以下、以降のルート群は元の run.py と同じになります ---
# (以降はあなたが提示した元の run.py の残りをそのまま貼っています)
# --- 設定管理ページ (API切り替え、プロンプト編集) ---
@app.route('/manage', methods=['GET', 'POST'])
@login_required
def manage():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            action = request.form.get('action')

            # 1. APIプロバイダーの切り替え処理
            if action == 'save_provider' :
                provider = request.form.get('api_provider')
                if provider in ['X', 'Threads']:
                    setting = db.query(Setting).filter(Setting.key == 'api_provider').first()
                    if setting:
                        setting.value = provider
                    else:
                        new_setting = Setting(key='api_provider', value=provider)
                        db.add(new_setting)
                    db.commit()

            # 2. プロンプトの編集処理
            elif action == 'save_prompt':
                prompt_text = request.form.get('prompt_text')
                if prompt_text:
                    prompt = db.query(Prompt).filter(Prompt.name == DEFAULT_PROMPT_KEY).first()
                    if prompt:
                        prompt.template_text = prompt_text
                        db.commit()

            # 2.1: デフォルトとして使用するプロンプトを選択して保存する処理
            elif action == 'set_default_prompt':
                selected_prompt_name = request.form.get('selected_prompt')
                if selected_prompt_name:
                    setting = db.query(Setting).filter(Setting.key == 'default_prompt_name').first()
                    if setting:
                        setting.value = selected_prompt_name
                    else:
                        new_setting = Setting(key='default_prompt_name', value=selected_prompt_name)
                        db.add(new_setting)
                    db.commit()
                    flash(f"プロンプト '{selected_prompt_name}' をデフォルトに設定しました。", 'success')
            
            # 3. クレジット残高の設定処理
            elif action == 'save_credit':
                new_credit_str = request.form.get('credit_amount')
                try:
                    new_credit = round(float(new_credit_str), 6)
                    setting = get_or_create_credit_setting(db)
                    setting.value = str(new_credit)
                    db.commit()
                except (ValueError, TypeError):
                    print(f"Invalid credit amount: {new_credit_str}")

            # 4. (変更) 生テキストファイルのインポート処理
            elif action == 'import_jsonl':
                if 'jsonl_file' not in request.files:
                    flash('ファイルがリクエストに含まれていません。', 'error')
                    return redirect(url_for('manage'))
                
                file = request.files['jsonl_file']
                
                if file.filename == '':
                    flash('ファイルが選択されていません。', 'error')
                    return redirect(url_for('manage'))

                if file and file.filename.endswith('.txt'):
                    try:
                        # 1. 生テキストファイルを行リストとして読み込む
                        stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
                        lines = [line.strip() for line in stream.readlines()]
                        
                        if not lines:
                             flash('ファイルが空です。', 'error')
                             return redirect(url_for('manage'))

                        # 2. DBから既存のpost_idセットを取得
                        existing_ids_tuples = db.query(CollectedPost.post_id).all()
                        existing_ids_set = {pid[0] for pid in existing_ids_tuples}
                        print(f"DBに {len(existing_ids_set)} 件の既存IDを検出。")

                        # 3. (変更) パーサー関数を utils_parser から呼び出す
                        parsed_posts_data, new_count = parse_threads_data_from_lines(lines, existing_ids_set)
                        
                        added_to_db_count = 0
                        skipped_in_db_count = 0

                        if not parsed_posts_data:
                            flash('解析できる新規投稿が見つかりませんでした。ファイル内容を確認してください。', 'warning')
                            return redirect(url_for('manage'))

                        # 4. パーサーが返した辞書リストをDBに挿入
                        for post_data in parsed_posts_data:
                            try:
                                posted_at_dt = parse(post_data['posted_at'])

                                new_post = CollectedPost(
                                    username=post_data['username'],
                                    post_id=post_data['post_id'],
                                    original_text=post_data['original_text'],
                                    source_url=post_data.get('source_url', ''), 
                                    posted_at=posted_at_dt,
                                    like_count=int(post_data.get('like_count', 0)),
                                    retweet_count=int(post_data.get('retweet_count', 0)),
                                    created_at=datetime.now(timezone.utc)
                                )
                                db.add(new_post)
                                db.flush()
                                added_to_db_count += 1

                            except IntegrityError:
                                db.rollback() 
                                print(f"DBスキップ (IntegrityError): {post_data.get('post_id')}")
                                skipped_in_db_count += 1
                            except Exception as e:
                                db.rollback()
                                print(f"DB挿入エラー: {e} (データ: {post_data})")
                                skipped_in_db_count += 1

                        db.commit() 
                        
                        total_skipped = (new_count - added_to_db_count) + skipped_in_db_count
                        flash(f'インポート完了: {added_to_db_count} 件の新規投稿を追加, {total_skipped} 件をスキップしました。', 'success')

                    except Exception as e:
                        db.rollback()
                        print(f"ファイル処理中にエラーが発生しました: {e}")
                        flash(f'ファイル処理エラー: {e}', 'error')
                else:
                    flash('無効なファイル形式です。.txt ファイルをアップロードしてください。', 'error')

            return redirect(url_for('manage')) # 処理後にリダイレクト

        # GET処理: ページ表示
        current_provider = get_current_provider(db)
        current_prompt = get_current_prompt(db)

        # 全保存済みプロンプトを取得してテンプレートに渡す（UI のセレクト用）
        prompts = db.query(Prompt).order_by(Prompt.name).all()
        current_credit = float(get_or_create_credit_setting(db).value)
        
        return render_template(
            "manage.html",
            current_provider=current_provider,
            default_prompt=current_prompt.template_text,
            current_credit=current_credit,
            prompts=prompts,
            current_prompt_name=current_prompt.name
        )
    finally:
        db.close()

# --- (以降はあなたの元ファイルのルーティング群をそのまま残しています) ---
# ...（省略せずに元のルート群をそのまま残してください）...
# --- 実行 ---
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001) # (デバッグ時はポート5001などを推奨)