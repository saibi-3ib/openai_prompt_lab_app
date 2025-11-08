import os
import json
import requests 
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, get_flashed_messages
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload, subqueryload
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from dateutil.parser import parse
import io
from dotenv import load_dotenv

# --- (変更) モデル定義とDB接続を models から持ってくる ---
from models import (
    SessionLocal, CollectedPost, Setting, Prompt, AnalysisResult, User, 
    TickerSentiment, StockTickerMap, TargetAccount, UserTickerWeight
)
from datetime import datetime, timezone

# --- ▼▼▼【新規】ロジックのインポート ▼▼▼ ---
from utils_parser import parse_threads_data_from_lines
from utils_db import (
    get_current_provider, get_or_create_credit_setting, get_current_prompt,
    run_batch_analysis, AVAILABLE_MODELS, client_openai, DEFAULT_PROMPT_KEY
)
# --- ▲▲▲ インポートここまで ▲▲▲ ---

load_dotenv()
app = Flask(__name__)

# .env ファイルに FLASK_SECRET_KEY を必ず設定するようにします
# (os.urandom() はサーバー再起動のたびにキーが変わり、セッションが切れるため非推奨)
app.secret_key = os.environ.get('FLASK_SECRET_KEY')
if not app.secret_key:
    raise ValueError("FLASK_SECRET_KEY が .env ファイルに設定されていません。")

# Flask-Login の初期化
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # 未ログイン時にリダイレクトされるページの関数名
login_manager.login_message = "このページにアクセスするにはログインが必要です。" # flash メッセージ
login_manager.login_message_category = "info" # flash メッセージのカテゴリ (任意)

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
        credit_setting = get_or_create_credit_setting(db)
        current_credit = float(credit_setting.value)
        
        return render_template(
            "manage.html", 
            current_provider=current_provider, 
            default_prompt=current_prompt.template_text,
            current_credit=current_credit,
        )
    finally:
        db.close()

# --- オンデマンドAI分析の実行 (単一) ---
@app.route('/analyze/<int:post_id>', methods=['POST'])
@login_required
def analyze_post(post_id):
    # (注: この単一分析ルートは現在 index.html から使われていませんが、残しておきます)
    if not client_openai:
        return jsonify({"status": "error", "message": "OpenAI API Key not configured."}), 400

    db = SessionLocal()
    try:
        post = db.query(CollectedPost).filter(CollectedPost.id == post_id).first()
        if not post:
            return jsonify({"status": "error", "message": "Post not found."}), 404
        
        current_prompt = get_current_prompt(db)
        full_prompt = current_prompt.template_text.replace("{text}", post.original_text)

        response = client_openai.chat.completions.create(
            model="gpt-3.5-turbo", # (単一の場合は3.5で固定)
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                {"role": "user", "content": full_prompt}
            ]
        )
        ai_result_str = response.choices[0].message.content
        ai_result_json = json.loads(ai_result_str)
        summary = ai_result_json.get("summary", "Summary not available.")

        new_result = AnalysisResult(
            prompt_id = current_prompt.id,
            raw_json_response = ai_result_str,
            extracted_summary = summary
        )
        new_result.posts.append(post)
        post.ai_summary = summary # (古いカラムにも互換性のために保存)
        db.add(new_result)
        db.commit()        

        return jsonify({"status": "success", "summary": summary})
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"AI analysis failed: {str(e)}"}), 500
    finally:
        db.close()

# --- (スリム化) 一括分析の実行 ---
@app.route('/api/analyze-batch', methods=['POST'])
@login_required
def analyze_batch():
    if not client_openai:
        return jsonify({"status": "error", "message": "OpenAI API Key not configured."}), 400

    data = request.get_json()
    
    # ▼▼▼【修正点】プロンプト名を取得して追加 ▼▼▼
    selected_prompt_name = data.get('promptName') # UIから送られたプロンプト名
    if not selected_prompt_name:
         return jsonify({"status": "error", "message": "プロンプト名が指定されていません。"}), 400
    
    try:
        # (変更) ビジネスロジックを utils_db の関数に委譲
        result_data = run_batch_analysis(
            post_ids=data.get('postIds', []),
            prompt_text=data.get('promptText'),
            selected_model=data.get('modelName', AVAILABLE_MODELS[0]),
            selected_prompt_name=selected_prompt_name
        )
        return jsonify(result_data)
    
    except Exception as e:
        error_msg = f"AI一括分析処理中にエラーが発生しました: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": "AI analysis failed", "details": error_msg}), 500
    # (注: db.close() は run_batch_analysis 内で実行されるため、ここでは不要)


# --- APIルート: 投稿の動的絞り込み ---
@app.route('/api/filter-posts', methods=['POST'])
@login_required
def filter_posts():
    db = SessionLocal()
    try:
        data = request.get_json()
        keyword = data.get('keyword')
        accounts = data.get('accounts', [])
        likes = data.get('likes')
        rts = data.get('rts')

        ticker_list = data.get('ticker')    # (これは前回修正済み)
        sentiment = data.get('sentiment')
        sectors = data.get('sector')        # (★ sector -> sectors 配列に変更)
        sub_sectors = data.get('sub_sector') # (★ sub_sector -> sub_sectors 配列に変更)

        query = db.query(CollectedPost)

        if keyword:
            query = query.filter(CollectedPost.original_text.ilike(f"%%{keyword}%%"))
        if accounts:
            query = query.filter(CollectedPost.username.in_(accounts))
        
       # センチメントまたはティッカーでの絞り込み
        if ticker_list or sentiment:
            query = query.join(TickerSentiment, CollectedPost.id == TickerSentiment.collected_post_id)
            
            if ticker_list:
                # (★ ilike ではなく 'in_' を使って配列で検索)
                query = query.filter(TickerSentiment.ticker.in_(ticker_list))
            
            if sentiment:
                query = query.filter(TickerSentiment.sentiment == sentiment)

        # セクターまたはサブセクターでの絞り込み
        if sectors or sub_sectors:
            if not (ticker_list or sentiment):
                 query = query.join(TickerSentiment, CollectedPost.id == TickerSentiment.collected_post_id)
            
            query = query.join(StockTickerMap, TickerSentiment.ticker == StockTickerMap.ticker)
            
            # (★ OR条件で絞り込み。sectors配列かsub_sectors配列の *いずれか* に一致)
            filters = []
            if sectors:
                filters.append(StockTickerMap.gics_sector.in_(sectors))
            if sub_sectors:
                filters.append(StockTickerMap.gics_sub_industry.in_(sub_sectors))
            
            if filters:
                from sqlalchemy import or_
                query = query.filter(or_(*filters))
        
        if likes is not None:
            try:
                likes_int = int(likes)
                if likes_int > 0:
                    query = query.filter(CollectedPost.like_count >= likes_int)
            except ValueError: pass
        if rts is not None:
            try:
                rts_int = int(rts)
                if rts_int > 0:
                    query = query.filter(CollectedPost.retweet_count >= rts_int)
            except ValueError: pass

        filtered_posts = query.order_by(CollectedPost.id.desc()).all()

        results_list = []
        for post in filtered_posts:
            results_list.append({
                "id": post.id,
                "username": post.username,
                "posted_at_iso": post.posted_at.isoformat() if post.posted_at else None, 
                "original_text": post.original_text,
                "source_url": post.source_url,
                "like_count": post.like_count,
                "retweet_count": post.retweet_count,
                "link_summary": post.link_summary
            })

        return jsonify({
            "status": "success",
            "count": len(results_list),
            "posts": results_list
        })
    except Exception as e:
        db.rollback()
        error_msg = f"絞り込み処理中にエラーが発生しました: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": error_msg}), 500
    finally:
        db.close()

# --- APIルート: オートサジェスト (ティッカー/セクター) ---
@app.route('/api/suggest', methods=['POST'])
@login_required
def suggest():
    db = SessionLocal()
    try:
        # (★) request.args.get から request.get_json() に変更
        data = request.get_json()
        query = data.get('q', '').strip()
        search_type = data.get('type', 'ticker') # 'ticker' or 'sector'

        if not query:
            return jsonify([])

        results_list = []
        
        if search_type == 'ticker':
            # StockTickerMap の ticker または company_name を検索
            query_filter = (
                StockTickerMap.ticker.ilike(f"%%{query}%%") |
                StockTickerMap.company_name.ilike(f"%%{query}%%")
            )
            # (注: .limit(10) を追加し、候補が多すぎないようにする)
            results = db.query(StockTickerMap).filter(query_filter).limit(10).all()
            for r in results:
                # (フロントエンドが使いやすいように "value" と "label" で返す)
                results_list.append({
                    "value": r.ticker,
                    "label": f"{r.ticker} ({r.company_name})"
                })
        
        elif search_type == 'sector':
            # StockTickerMap の gics_sector を検索 (重複除去)
            query_filter = StockTickerMap.gics_sector.ilike(f"%%{query}%%")
            results = db.query(StockTickerMap.gics_sector).filter(query_filter).distinct().limit(10).all()
            for r in results:
                if r[0]: # (NULLを除外)
                    results_list.append({
                        "value": r[0],
                        "label": r[0]
                    })

        return jsonify(results_list)
    
    except Exception as e:
        db.rollback()
        error_msg = f"サジェスト検索中にエラーが発生しました: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": error_msg}), 500
    finally:
        db.close()

# --- APIルート: 保存済みプロンプト一覧の取得 ---
@app.route('/api/get-prompts', methods=['GET'])
@login_required
def get_prompts():
    db = SessionLocal()
    try:
        prompts = db.query(Prompt).order_by(Prompt.name).all()
        results_list = []
        for p in prompts:
            results_list.append({
                "id": p.id,
                "name": p.name,
                "template_text": p.template_text,
                "is_default": p.is_default
            })
        
        if not results_list:
            default_prompt = get_current_prompt(db) # (utils_db から呼び出し)
            results_list.append({
                "id": default_prompt.id,
                "name": default_prompt.name,
                "template_text": default_prompt.template_text,
                "is_default": default_prompt.is_default
            })

        return jsonify(results_list)
    except Exception as e:
        error_msg = f"プロンプトの読み込み中にエラーが発生しました: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": error_msg}), 500
    finally:
        db.close()

# --- APIルート: プロンプトの保存/更新 ---
@app.route('/api/save-prompt', methods=['POST'])
@login_required
def save_prompt():
    db = SessionLocal()
    try:
        data = request.get_json()
        prompt_id = data.get('promptId')
        prompt_text = data.get('templateText')
        prompt_name = data.get('promptName')

        if not prompt_text:
            return jsonify({"status": "error", "message": "プロンプト本文が空です。"}), 400

        if prompt_id:
            # --- 更新 ---
            prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
            if not prompt:
                return jsonify({"status": "error", "message": "対象のプロンプトが見つかりません。"}), 404
            
            prompt.template_text = prompt_text
            db.commit()
            db.refresh(prompt)
            
            return jsonify({
                "status": "success", 
                "message": f"プロンプト '{prompt.name}' を更新しました。",
                "action": "update",
                "updated_prompt": {
                    "id": prompt.id,
                    "name": prompt.name,
                    "template_text": prompt.template_text,
                    "is_default": prompt.is_default
                }
            })
        
        else:
            # --- 新規作成 ---
            if not prompt_name:
                return jsonify({"status": "error", "message": "新しいプロンプトの名前を入力してください。"}), 400
            
            existing = db.query(Prompt).filter(Prompt.name == prompt_name).first()
            if existing:
                return jsonify({"status": "error", "message": f"名前 '{prompt_name}' は既に使用されています。"}), 409

            new_prompt = Prompt(
                name = prompt_name,
                template_text = prompt_text,
                is_default = False
            )
            db.add(new_prompt)
            db.commit()
            db.refresh(new_prompt)
            
            return jsonify({
                "status": "success",
                "message": f"プロンプト '{new_prompt.name}' を新規保存しました。",
                "action": "create",
                "new_prompt": {
                    "id": new_prompt.id,
                    "name": new_prompt.name,
                    "template_text": new_prompt.template_text,
                    "is_default": new_prompt.is_default
                }
            })
    except Exception as e:
        db.rollback()
        error_msg = f"プロンプト保存中にエラーが発生しました: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": error_msg}), 500
    finally:
        db.close()

# --- APIルート: プロンプトの削除 ---
@app.route('/api/delete-prompt', methods=['POST'])
@login_required
def delete_prompt():
    db = SessionLocal()
    try:
        data = request.get_json()
        prompt_id = data.get('promptId')

        if not prompt_id:
            return jsonify({"status": "error", "message": "プロンプトIDが指定されていません。"}), 400

        prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()

        if not prompt:
            return jsonify({"status": "error", "message": "削除対象のプロンプトが見つかりません。"}), 404
        
        if prompt.is_default or prompt.name == DEFAULT_PROMPT_KEY:
            return jsonify({"status": "error", "message": "デフォルトプロンプト (default_summary) は削除できません。"}), 403

        deleted_name = prompt.name
        db.delete(prompt)
        db.commit()
        
        return jsonify({
            "status": "success", 
            "message": f"プロンプト '{deleted_name}' を削除しました。"
        })
    except Exception as e:
        db.rollback()
        error_msg = f"プロンプト削除中にエラーが発生しました: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": error_msg}), 500
    finally:
        db.close()

# --- ページ: 分析履歴一覧 ---
@app.route('/history')
@login_required
def history():
    db = SessionLocal()
    try:
        results = db.query(AnalysisResult).options(
            joinedload(AnalysisResult.prompt),
            joinedload(AnalysisResult.posts),
            # (★) TickerSentiment と、それに関連する投稿(本文)も読み込む
            joinedload(AnalysisResult.sentiments).joinedload(TickerSentiment.collected_post)
        ).order_by(AnalysisResult.analyzed_at.desc()).all()
        
        return render_template("history.html", results=results)

    except Exception as e:
        print(f"履歴ページの読み込みエラー: {e}")
        flash(f"履歴の読み込みに失敗しました: {e}", "error")
        return redirect(url_for('index'))
    finally:
        db.close()

# --- ▼▼▼【以下を追加: ログイン/ログアウト ルート】▼▼▼ ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    # 既にログイン済みの場合はダッシュボードへリダイレクト
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember') # (今回は使わないが、将来の「ログイン状態を保持」用)

        db = SessionLocal()
        user = db.query(User).filter_by(username=username).first()
        db.close()

        # ユーザーが存在し、パスワードが正しいかチェック
        if user and check_password(user.password_hash, password):
            # Flask-Login の login_user 関数を呼び出す
            login_user(user, remember=remember) # remember は True/False

            # ログイン後にリダイレクトすべきページがあればそこへ、なければダッシュボードへ
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('index')
            flash('ログインしました。', 'success')
            return redirect(next_page)
        else:
            flash('ユーザー名またはパスワードが無効です。', 'error')

    # GET リクエスト、またはログイン失敗時はログインページを表示
    return render_template('login.html')

@app.route('/logout')
@login_required # ログアウトはログインしているユーザーのみ実行可能
def logout():
    logout_user() # Flask-Login の logout_user 関数
    flash('ログアウトしました。', 'info')
    return redirect(url_for('login')) # ログアウト後はログインページへ
# --- ▲▲▲【ログイン/ログアウト ルートここまで】▲▲▲ ---

# --- ▼▼▼【ここから追加】アカウント管理ページ ▼▼▼ ---
@app.route('/accounts', methods=['GET', 'POST'])
@login_required
def accounts():
    db = SessionLocal()
    try:
        # --- POSTリクエスト処理 (アカウントの追加・削除・トグル) ---
        if request.method == 'POST':
            action = request.form.get('action')
            
            # (1) アカウントの新規追加
            if action == 'add_account':
                username = request.form.get('username')
                provider = request.form.get('provider', 'X') # デフォルトは 'X'
                if not username:
                    flash('アカウント名を入力してください。', 'error')
                else:
                    existing = db.query(TargetAccount).filter(TargetAccount.username == username).first()
                    if existing:
                        flash(f"アカウント '{username}' は既に存在します。", 'warning')
                    else:
                        new_account = TargetAccount(
                            username=username,
                            provider=provider,
                            is_active=True # (★) 追加時はデフォルトで有効
                        )
                        db.add(new_account)
                        db.commit()
                        flash(f"アカウント '{username}' ({provider}) を追加しました。", 'success')

            # (2) アカウントの削除
            elif action == 'delete_account':
                account_id = request.form.get('account_id')
                account = db.query(TargetAccount).filter(TargetAccount.id == account_id).first()
                if account:
                    # (★) 安全のため、関連する重み付けデータも先に削除
                    db.query(UserTickerWeight).filter(UserTickerWeight.account_id == account_id).delete()
                    # (★) 関連する投稿データ (CollectedPost) は、アカウントを削除しても残す（仕様）
                    
                    db.delete(account)
                    db.commit()
                    flash(f"アカウント '{account.username}' を削除しました。", 'success')
                else:
                    flash('削除対象のアカウントが見つかりません。', 'error')
            
            # (3) アカウントの有効/無効トグル
            elif action == 'toggle_active':
                account_id = request.form.get('account_id')
                account = db.query(TargetAccount).filter(TargetAccount.id == account_id).first()
                if account:
                    account.is_active = not account.is_active
                    db.commit()
                    status = "有効化" if account.is_active else "無効化"
                    flash(f"アカウント '{account.username}' を{status}しました。", 'info')
                else:
                    flash('対象のアカウントが見つかりません。', 'error')
            
            return redirect(url_for('accounts')) # POST処理後は必ずリダイレクト

        # --- GETリクエスト処理 (ページ表示) ---
        
        # (★) 全アカウントを、関連データ（weights, posts）を含めて読み込む
        all_accounts = db.query(TargetAccount).options(
            # (★) 関連する weights（重み）を読み込む
            # joinedload(TargetAccount.weights),
            # (★) 関連する posts（投稿）を読み込む (lazy='dynamic' のため .all() は不要)
            # joinedload(TargetAccount.posts) 
            # selectinload(TargetAccount.weights)
            # subqueryload(TargetAccount.weights)
        ).order_by(TargetAccount.username).all()

        return render_template("accounts.html", accounts=all_accounts)

    except Exception as e:
        db.rollback()
        print(f"アカウント管理ページでエラー: {e}")
        flash(f"処理中にエラーが発生しました: {e}", "error")
        return redirect(url_for('index'))
    finally:
        db.close()
# --- ▲▲▲【追加ここまで】▲▲▲ ---


# --- 実行 ---
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001) # (デバッグ時はポート5001などを推奨)