import os
import json
import requests 
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, get_flashed_messages
from sqlalchemy.exc import IntegrityError # 重複エラー検出のため
from sqlalchemy.orm import joinedload
from dateutil.parser import parse # ISO形式の日時文字列をパースするため
import io # アップロードされたファイルをテキストとして読み込むため

from models import SessionLocal, CollectedPost, Setting, Prompt, AnalysisResult
from datetime import datetime, timezone, timedelta
import openai
from dotenv import load_dotenv

import re
import hashlib
from typing import List, Set, Tuple, Dict


load_dotenv()

app = Flask(__name__)

# ▼▼▼ Flashメッセージ機能に必要な Secret Key を設定 ▼▼▼
# (セッション管理のために必須。ない場合は flash() がエラーになります)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
# ▲▲▲ 追加ここまで ▲▲▲

# --- 設定値と初期化 ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client_openai = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
# プロンプト編集機能のための初期プロンプト名
DEFAULT_PROMPT_KEY = "default_summary"

# 選択可能なOpenAIモデル
AVAILABLE_MODELS = ["gpt-4o-mini", "gpt-3.5-turbo"] # 必要に応じてモデルを追加

# --- OpenAI コスト計算定数と関数 ---

# 2024年10月時点の OpenAI 公開価格 (USD/1Mトークン) - 概算値
# ※価格は変動します。必要に応じて調整してください。
COST_PER_MILLION = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    # 他のモデルもここに追加可能
}

def calculate_cost(model_name: str, usage: dict) -> float:
    """トークン使用量から概算コスト (USD) を計算する"""
    if model_name not in COST_PER_MILLION:
        print(f"Warning: Cost data for model {model_name} is missing.")
        return 0.0

    input_cost = COST_PER_MILLION[model_name]["input"]
    output_cost = COST_PER_MILLION[model_name]["output"]

    # トークン数を100万で割り、単価をかける
    total_cost = (usage.get("prompt_tokens", 0) / 1_000_000) * input_cost + \
                 (usage.get("completion_tokens", 0) / 1_000_000) * output_cost
    
    # 小数点以下8桁で丸めて返す
    return round(total_cost, 8)

# --- OpenAI 残クレジット計算用の関数 ---

def get_current_credit(db) -> float:
    """DBから現在の残高（クレジット）を取得する"""
    setting = db.query(Setting).filter(Setting.key == 'openai_total_credit').first()
    # 見つからない場合は初期値（例：0.00 USD）を設定するロジックが必要です
    if setting:
        try:
            return float(setting.value)
        except ValueError:
            print("Warning: openai_total_credit is not a valid float. Resetting to 0.")
            return 0.0
    
    # クレジット設定がDBにない場合は、0.00を初期値として挿入し、0を返す
    new_setting = Setting(key='openai_total_credit', value='0.00')
    db.add(new_setting)
    db.commit()
    return 0.0

def update_credit_balance(db, cost_usd: float) -> float:
    """残高から消費コストを差し引き、DBを更新する"""
    setting = db.query(Setting).filter(Setting.key == 'openai_total_credit').first()
    if not setting:
        return 0.0 # 設定がなければ更新スキップ

    try:
        current_balance = float(setting.value)
        new_balance = current_balance - cost_usd
        
        # データベースを更新
        setting.value = str(round(new_balance, 8))
        # コミットは呼び出し元の analyze_batch でまとめて行う
        
        return new_balance
    except ValueError as e:
        print(f"Error updating credit balance: {e}")
        return current_balance

def get_or_create_credit_setting(db, initial_value='20.000000') -> Setting:
    """DBからOpenAIクレジット設定を取得。なければ初期値で作成し、そのSettingオブジェクトを返す。"""
    key = 'openai_total_credit'
    setting = db.query(Setting).filter(Setting.key == key).first()
    
    if not setting:
        new_setting = Setting(key=key, value=initial_value)
        db.add(new_setting)
        db.commit()
        return new_setting
    return setting

# ▼▼▼【ここからパーサー関数を移植 (修正版)】▼▼▼
def parse_relative_time(time_str: str) -> str:
    """ 日本語の相対時間をISO 8601形式に変換（改善版） """
    now = datetime.now(timezone.utc)
    try:
        time_str = time_str.strip()
        if '分前' in time_str:
            minutes = int(re.search(r'(\d+)分前', time_str).group(1))
            post_time = now - timedelta(minutes=minutes)
        elif '時間前' in time_str:
            hours = int(re.search(r'(\d+)時間前', time_str).group(1))
            post_time = now - timedelta(hours=hours)
        elif '時間' in time_str: # 「前」がないパターン (例: "6時間")
            hours = int(re.search(r'(\d+)時間', time_str).group(1))
            post_time = now - timedelta(hours=hours)
        elif '昨日' in time_str:
            post_time = (now - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
        elif '日' in time_str and not ('月' in time_str or '年' in time_str): # 「X日」 (例: "1日", "3日")
            days = int(re.search(r'(\d+)日', time_str).group(1))
            post_time = now - timedelta(days=days)
        elif re.match(r'^\d+月\d+日$', time_str): # "X月X日"
            match = re.search(r'(\d+)月(\d+)日', time_str)
            month = int(match.group(1))
            day = int(match.group(2))
            post_time = now.replace(month=month, day=day, hour=12, minute=0, second=0, microsecond=0)
        elif '年' in time_str and '月' in time_str and '日' in time_str: # "X年X月X日"
             match = re.search(r'(\d+)年(\d+)月(\d+)日', time_str)
             year = int(match.group(1))
             month = int(match.group(2))
             day = int(match.group(3))
             post_time = now.replace(year=year, month=month, day=day, hour=12, minute=0, second=0, microsecond=0)
        elif re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', time_str): # "YYYY/MM/DD"
            post_time = datetime.strptime(time_str, '%Y/%m/%d').replace(tzinfo=timezone.utc)
        else:
             post_time = now
        return post_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception as e:
        print(f"[Parser Error] 時間文字列 '{time_str}' 解析失敗: {e}。")
        return now.strftime('%Y-%m-%dT%H:%M:%SZ')

def generate_pseudo_id(username: str, timestamp: str, text_snippet: str) -> str:
    """ 投稿IDの代替となるハッシュ値を生成 """
    # --- (↓ ここから4スペースのインデントが必須) ---
    ts_stable = timestamp[:16] if len(timestamp) >= 16 else timestamp
    snippet = text_snippet[:30] if text_snippet else "empty"
    hash_input = f"{username}-{ts_stable}-{snippet}"
    return hashlib.md5(hash_input.encode('utf-8')).hexdigest()[:10]
    # --- (↑ ここまでインデント) ---

def parse_threads_data_from_lines(lines: List[str], processed_ids_set: Set[str]) -> Tuple[List[Dict], int]:
    """ 
    (v14改) 生テキストの「行リスト」を受け取り、パース結果の「辞書リスト」を返す 
    """
    # --- (↓ ここから4スペースのインデントが必須) ---
    if not lines:
        print("[Parser Error] ファイルが空です。")
        return [], 0

    # --- アカウントID検出 ---
    account_id = None
    account_id_line_index = -1
    account_id_pattern_strict = r'^[\w.]{5,30}$'
    for i in range(min(15, len(lines))):
        stripped_line = lines[i]
        if re.fullmatch(account_id_pattern_strict, stripped_line):
             account_id = stripped_line
             account_id_line_index = i
             print(f"[Parser] アカウントID候補: '{account_id}' を {i+1} 行目で検出。")
             break

    if not account_id:
        print("[Parser Error] ファイルの先頭15行からアカウントID候補が見つかりませんでした。")
        return [], 0
    
    parsed_posts_data = [] # (変更) JSON文字列ではなく辞書を格納
    newly_added_count = 0
    
    # --- タイムスタンプ行を基準に投稿ブロックを特定 ---
    time_pattern = r'^(\d+分前|\d+時間前|\d+時間|\d+日|昨日|\d+月\d+日|\d+年\d+月\d+日|\d{4}/\d{1,2}/\d{1,2})$'
    post_starts = [] 
    search_start_line = account_id_line_index
    
    i = search_start_line
    while i < len(lines) - 1:
        current_line_stripped = lines[i]
        next_line_stripped = lines[i+1]

        # パターンA
        if current_line_stripped == account_id and re.match(time_pattern, next_line_stripped):
            post_starts.append((i, i + 1)) 
            i += 1 
            continue
        # パターンB
        elif re.match(r'^\d+$', current_line_stripped) and i + 4 < len(lines):
             if lines[i+1] == '/' and \
                re.match(r'^\d+$', lines[i+2]) and \
                lines[i+3] == account_id and \
                re.match(time_pattern, lines[i+4]):
                 post_starts.append((i + 3, i + 4)) 
                 i += 4 
                 continue
        i += 1 

    if not post_starts:
        print("[Parser Error] 有効な投稿開始パターンが見つかりません。")
        return [], 0

    print(f"[Parser] {len(post_starts)} 件の投稿開始点を検出しました。")

    # --- 各開始点から投稿データを抽出 ---
    for i in range(len(post_starts)):
        account_id_idx, timestamp_idx = post_starts[i]
        timestamp_str = lines[timestamp_idx]
        
        end_line_idx = post_starts[i+1][0] -1 if i + 1 < len(post_starts) else len(lines) - 1
        extract_start_idx = timestamp_idx + 1
        post_block_lines = lines[extract_start_idx : end_line_idx + 1]

        if not post_block_lines: continue

        data = {
            "username": account_id,
            "posted_at": parse_relative_time(timestamp_str),
            "like_count": 0,
            "retweet_count": 0
        }

        body_lines = []
        thread_num_pattern = r'^\d+\s*/\s*\d+$' # "1 / 2"

        for line in post_block_lines:
            if not line: continue
            if re.match(r'いいね！', line): break
            if re.search(r'件の返信', line): break
            if re.match(thread_num_pattern, line): break
            if line.startswith('http://') or line.startswith('https://'): break
            if line.startswith('amzn.to') or line.startswith('a.r10.to'): break
            if "翻訳" not in line and line != account_id: 
                 body_lines.append(line)

        post_text = "\n".join(body_lines).strip()
        data["original_text"] = post_text
        
        for line in reversed(post_block_lines):
            if not data["like_count"]: 
                like_match = re.search(r'いいね！([\d,]+)', line)
                if like_match: data["like_count"] = int(like_match.group(1).replace(',', ''))
            if not data["retweet_count"]: 
                 reply_match = re.search(r'([\d,]+)\s*件の返信', line)
                 if reply_match: data["retweet_count"] = int(reply_match.group(1).replace(',', ''))
            if data["like_count"] > 0 and data["retweet_count"] > 0:
                 break 

        pseudo_id = generate_pseudo_id(account_id, data["posted_at"], post_text)
        data["post_id"] = pseudo_id
        data["source_url"] = "" # (生テキストからはURLは取得できない)

        if pseudo_id not in processed_ids_set:
            if data["original_text"]: # 本文が空でないもののみ
                parsed_posts_data.append(data) # (変更) D辞書を直接追加
                processed_ids_set.add(pseudo_id) # (重要) DB保存前にセットに追加
                newly_added_count += 1
            else:
                 print(f"[Parser] post_id {pseudo_id} は本文が空のためスキップ")
        else:
             print(f"[Parser] post_id {pseudo_id} は処理済(重複)のためスキップ")

    print(f"[Parser] 処理完了: {newly_added_count} 件の新規投稿を抽出")
    
    # (変更) 辞書のリストと件数を返す
    return parsed_posts_data, newly_added_count 
    # --- (↑ ここまでインデント) ---
# ▲▲▲【パーサー関数ここまで】▲▲▲

# --- DB操作ヘルパー関数 ---
def get_current_provider(db):
    """DBから現在のAPIプロバイダー設定を取得する"""
    setting = db.query(Setting).filter(Setting.key == 'api_provider').first()
    return setting.value if setting else 'X'

def get_current_prompt(db):
    """DBからデフォルトのプロンプトを取得する。なければ初期値を作成する。"""
    prompt = db.query(Prompt).filter(Prompt.name == DEFAULT_PROMPT_KEY).first()
    if not prompt:
        # DBにプロンプトがなければ初期値を作成
        default_text = """
        以下の英語の文章を日本語に翻訳し、投資家向けの視点で最も重要なポイントを1つの短い文で要約してください。

        結果は必ず以下のJSON形式で返してください。
        {{
          "translation": "ここに翻訳結果",
          "summary": "ここに要約結果"
        }}

        原文:
        {text}
        """
        new_prompt = Prompt(name=DEFAULT_PROMPT_KEY, template_text=default_text, is_default=True)
        db.add(new_prompt)
        db.commit()
        return new_prompt
    return prompt

def get_or_create_credit_setting(db, initial_value='18.000000') -> Setting:
    """DBからOpenAIクレジット設定を取得。なければ初期値で作成し、そのSettingオブジェクトを返す。"""
    key = 'openai_total_credit'
    setting = db.query(Setting).filter(Setting.key == key).first()
    
    if not setting:
        # DBに設定がなければ初期値を作成
        new_setting = Setting(key=key, value=initial_value)
        db.add(new_setting)
        db.commit()
        # commit 後にセッションからオブジェクトを再取得またはリフレッシュ（ここではシンプルにオブジェクトを返す）
        return new_setting
    return setting

# --- メインページ (データ表示) ---
@app.route('/')
def index():
    db = SessionLocal()
    try:
        posts = db.query(CollectedPost).order_by(CollectedPost.id.desc()).limit(50).all()
        # API設定を読み込み
        current_provider = get_current_provider(db)
   
        # 現在のクレジット残高を取得 (なければ初期化)
        credit_setting = get_or_create_credit_setting(db)
        current_credit = float(credit_setting.value)
        
        # ▼▼▼【ここから追加】▼▼▼
        # DBからユニークなアカウント名を取得する
        # (username, ) というタプルのリストが返るので、[0]で取り出してリスト化
        account_names_tuples = db.query(CollectedPost.username).distinct().order_by(CollectedPost.username).all()
        available_accounts = [name[0] for name in account_names_tuples]
        # ▲▲▲【ここまで追加】▲▲▲

        return render_template(
            "index.html", 
            posts=posts, 
            current_provider=current_provider,
            current_credit=current_credit,
            available_models=AVAILABLE_MODELS,
            available_accounts=available_accounts
        )
    finally:
        db.close()

# --- 設定管理ページ (API切り替え、プロンプト編集) ---
@app.route('/manage', methods=['GET', 'POST'])
def manage():
    db = SessionLocal()
    try:
        # POST処理: APIプロバイダーの切り替え
        if request.method == 'POST':
            action = request.form.get('action')
            print(f"Form action: {action}")  # デバッグ用ログ

            # 1. APIプロバイダーの切り替え処理
            if action == 'save_provider' :
                provider = request.form.get('api_provider')
                print(f"Selected provider: {provider}")  # デバッグ用ログ

                if provider in ['X', 'Threads']:
                    setting = db.query(Setting).filter(Setting.key == 'api_provider').first()
                    if setting:
                        setting.value = provider
                    else:
                        new_setting = Setting(key='api_provider', value=provider)
                        db.add(new_setting)
                    db.commit()
                    print(f"debug: commit successful for provider {provider}")
                else:
                    print(f"Invalid provider selected: {provider}")

            # 2. プロンプトの編集処理
            elif action == 'save_prompt':
                prompt_text = request.form.get('prompt_text')

                if prompt_text:
                    prompt = db.query(Prompt).filter(Prompt.name == DEFAULT_PROMPT_KEY).first()
                    if prompt:
                        prompt.template_text = prompt_text
                        db.commit()
                        print(f"debug: commit successful for prompt")
            
            # ▼▼▼【新規】3. クレジット残高の設定処理 ▼▼▼
            elif action == 'save_credit':
                new_credit_str = request.form.get('credit_amount')
                try:
                    # 数値かチェックし、小数点以下6桁の文字列に変換
                    new_credit = round(float(new_credit_str), 6)
                    setting = get_or_create_credit_setting(db)
                    setting.value = str(new_credit)
                    db.commit()
                    print(f"debug: commit successful for credit {new_credit}")
                except (ValueError, TypeError):
                    print(f"Invalid credit amount: {new_credit_str}")

            # ▼▼▼【新規】JSON Linesファイルの一括インポート処理 ▼▼▼
            # ▼▼▼【ここからロジックを置き換え】▼▼▼
            # (旧: import_jsonl / 新: import_raw_text)
            # HTML側の value="import_jsonl" はそのまま利用し、
            # バックエンドの処理を生テキストパーサーに差し替える
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
                        # 1. (変更) 生テキストファイルを行リストとして読み込む
                        stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
                        lines = [line.strip() for line in stream.readlines()]
                        
                        if not lines:
                             flash('ファイルが空です。', 'error')
                             return redirect(url_for('manage'))

                        # 2. (変更) DBから既存のpost_idセットを取得
                        existing_ids_tuples = db.query(CollectedPost.post_id).all()
                        existing_ids_set = {pid[0] for pid in existing_ids_tuples}
                        initial_id_count = len(existing_ids_set)
                        print(f"DBに {initial_id_count} 件の既存IDを検出。")

                        # 3. (変更) 移植したパーサー関数を実行
                        #    (existing_ids_set は参照渡しされ、パーサー内で更新される)
                        parsed_posts_data, new_count = parse_threads_data_from_lines(lines, existing_ids_set)
                        
                        added_to_db_count = 0
                        skipped_in_db_count = 0

                        if not parsed_posts_data:
                            flash('解析できる新規投稿が見つかりませんでした。ファイル内容を確認してください。', 'warning')
                            return redirect(url_for('manage'))

                        # 4. (変更) パーサーが返した辞書リストをDBに挿入
                        for post_data in parsed_posts_data:
                            try:
                                # 念のため、パーサーが生成したIDがDBにないか最終チェック
                                # (parse_threads_data_from_lines内で既にチェック＆セット追加済みだが二重確認)
                                if post_data['post_id'] in existing_ids_set:
                                    # (このルートは通常通らないはず)
                                    print(f"DBスキップ: {post_data['post_id']} は既にDBに存在。")
                                    skipped_in_db_count += 1
                                    continue

                                # 投稿日時 (posted_at) をISO文字列からdatetimeオブジェクトに変換
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
                                db.flush() # flushしてDBに送信 (commit前)
                                added_to_db_count += 1
                                # (パーサーがセットに追加済みなので、ここでは不要)
                                # existing_ids_set.add(post_data['post_id'])

                            except IntegrityError: # post_id の unique 制約違反
                                db.rollback() 
                                print(f"DBスキップ (IntegrityError): {post_data.get('post_id')}")
                                skipped_in_db_count += 1
                            except Exception as e:
                                db.rollback()
                                print(f"DB挿入エラー: {e} (データ: {post_data})")
                                skipped_in_db_count += 1

                        # 5. すべての処理が終わったらコミット
                        db.commit() 
                        
                        # パーサーが検出した新規件数(new_count)と、
                        # 実際にDBに追加成功した件数(added_to_db_count)
                        total_skipped = (new_count - added_to_db_count) + skipped_in_db_count
                        flash(f'インポート完了: {added_to_db_count} 件の新規投稿を追加, {total_skipped} 件をスキップしました。', 'success')

                    except Exception as e:
                        db.rollback()
                        print(f"ファイル処理中にエラーが発生しました: {e}")
                        flash(f'ファイル処理エラー: {e}', 'error')
                else:
                    flash('無効なファイル形式です。.txt ファイルをアップロードしてください。', 'error')
            # ▲▲▲【ロジック置き換えここまで】▲▲▲

            return redirect(url_for('manage')) # 処理後にリダイレクト

        # GET処理: ページ表示
        current_provider = get_current_provider(db)
        current_prompt = get_current_prompt(db)
        
        # ▼▼▼【修正点】クレジット設定を読み込み (なければここで挿入される) ▼▼▼
        credit_setting = get_or_create_credit_setting(db)
        current_credit = float(credit_setting.value) # ここで current_credit を定義
        
        return render_template(
            "manage.html", 
            current_provider=current_provider, 
            default_prompt=current_prompt.template_text,
            current_credit=current_credit, # ★★★ ここで渡す ★★★
        )
    finally:
        db.close()

# --- オンデマンドAI分析の実行 ---
@app.route('/analyze/<int:post_id>', methods=['POST'])
def analyze_post(post_id):
    if not client_openai:
        # DB接続を試みる前のエラーハンドリングでリソース節約
        return jsonify({"status": "error", "message": "OpenAI API Key not configured."}), 400

    db = SessionLocal()
    try:
        post = db.query(CollectedPost).filter(CollectedPost.id == post_id).first()
        if not post:
            return jsonify({"status": "error", "message": "Post not found."}), 404

        # dbから現在のプロンプトテンプレートを取得
        current_prompt = get_current_prompt(db)
        
        # プロンプトテンプレートに元のテキストを挿入
        # {text} を元の投稿テキストで置換
        full_prompt = current_prompt.template_text.replace("{text}", post.original_text)

        # AI呼び出しのロジックをここに記述
        response = client_openai.chat.completions.create(
            model="gpt-3.5-turbo",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                {"role": "user", "content": full_prompt}
            ]
        )
        ai_result_str = response.choices[0].message.content

        # JSON文字列をパース
        ai_result_json = json.loads(ai_result_str)
        summary = ai_result_json.get("summary", "Summary not available.")

        # 新しいAnalysisResultレコードを作成
        new_result = AnalysisResult(
            prompt_id = current_prompt.id,
            raw_json_response = ai_result_str,
            extracted_summary = summary
            # 将来的に必要に応じて他のフィールドも追加(センチメント分析など)
            # extracted_sentiment = ai_result_json.get("sentiment")
        )

        # どの投稿を使ったかを関連付ける(多対多のリンク)
        new_result.posts.append(post)

        # UIの互換性のため、古いカラムにも一時的にサマリーを保存
        post.ai_summary = summary

        # データベースを更新
        db.add(new_result)
        db.commit()        

        return jsonify({"status": "success", "summary": summary})

    except Exception as e:
        db.rollback()
        error_msg = f"AI分析処理中にエラーが発生しました: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": f"AI analysis failed: {str(e)}"}), 500
    finally:
        db.close()

# --- 新しいAPIルート: 複数のポストを一括分析する ---
@app.route('/api/analyze-batch', methods=['POST'])
def analyze_batch():
    if not client_openai:
        return jsonify({"status": "error", "message": "OpenAI API Key not configured."}), 400

    # 1. リクエストボディからデータを受信
    data = request.get_json()
    post_ids = data.get('postIds', [])
    prompt_text = data.get('promptText')
    selected_model = data.get('modelName', AVAILABLE_MODELS[0]) # 指定がなければ最初のモデルをデフォルトに

    if not post_ids or not prompt_text:
        return jsonify({"status": "error", "message": "投稿IDのリストとプロンプトテキストが必要です。"}), 400
    
    db = SessionLocal()
    
    try:
        # 2. データベースから複数の投稿を一度に取得
        #   in_() を使うことで、効率的に複数のIDの投稿を取得できます。
        posts = db.query(CollectedPost).filter(CollectedPost.id.in_(post_ids)).all()
        
        if not posts:
            return jsonify({"status": "error", "message": "選択された投稿IDに対応するデータが見つかりませんでした。"}), 404

        # 3. 複数の投稿テキストを結合して、AIに渡す文字列を作成
        #    - 各投稿を改行と区切り線で結合し、AIが処理しやすいようにします。
        combined_texts = ""
        for i, post in enumerate(posts):
            # 投稿をリスト化して番号を振る
            combined_texts += f"--- POST {i+1} (ID:{post.post_id}) ---\n"
            combined_texts += post.original_text + "\n\n"
        
        # 4. プロンプト変数を置換
        #    - {texts} を結合したテキストで置換
        full_prompt = prompt_text.replace("{texts}", combined_texts)
        #    - {text} が残っている場合は、AIに指示を出す文章に置き換えます（念のため）
        full_prompt = full_prompt.replace("{text}", "[警告: {text} 変数は単数分析用です。{texts} を使用してください。]")


        # 使用モデルの固定（UI実装までの仮措置）
        ANALYSIS_MODEL = "gpt-3.5-turbo" # 当面はこのモデルで固定

        # 5. AI呼び出しの実行
        #    - 複数ポストの処理には、より高性能なモデル (gpt-4o-miniなど) を推奨しますが、
        #      まずは gpt-3.5-turbo でテストします。
        response = client_openai.chat.completions.create(
            model=selected_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output JSON. You are analyzing multiple social media posts about investing. Your output must summarize the core sentiment and investment topics discussed across ALL provided posts."},
                {"role": "user", "content": full_prompt}
            ]
        )

        ai_result_str = response.choices[0].message.content
        
        # トークン使用量を取得 
        usage_data = response.usage.model_dump() # トークン使用量の辞書

        # 6. JSON結果のパースと保存 (修正後のコード)
        ai_result_json = json.loads(ai_result_str)
        # summary のパースは引き続き行い、extracted_summary に格納する
        summary = ai_result_json.get("summary", "Summary not available.")

        # ▼▼▼【ここから修正】▼▼▼
        # 複数のキーを試行してサマリーを抽出
        summary = ai_result_json.get("analysis_summary", None) # (1) Sentiment_v1 形式
        if summary is None:
            summary = ai_result_json.get("summary", "Summary not available.") # (2) default_summary 形式
        # ▲▲▲【ここまで修正】▲▲▲

        # コスト計算
        total_cost = calculate_cost(selected_model, usage_data)
        # クレジット残高を更新
        new_balance = update_credit_balance(db, total_cost)

        # 新しい AnalysisResult レコードを作成 (履歴として保存)
        current_prompt = db.query(Prompt).filter(Prompt.name == DEFAULT_PROMPT_KEY).first()

        new_result = AnalysisResult(
            prompt_id = current_prompt.id if current_prompt else 1, 
            # ▼▼▼ 修正点: raw_json_response に AIからの生文字列全体を保存 ▼▼▼
            raw_json_response = ai_result_str, 
            # ▼▼▼ 修正点: extracted_summary にパースした summary の値を保存 ▼▼▼
            extracted_summary = summary,
            # ▼▼▼【修正点4】モデルとコストの保存 ▼▼▼
            ai_model = ANALYSIS_MODEL,
            cost_usd = total_cost            
        )

        # 7. 多対多の関連付け
        for post in posts:
            new_result.posts.append(post) # 選択された全ての投稿をリンク
        
        # 8. データベースにコミット
        db.add(new_result)
        db.commit()
        
        # 成功レスポンス
        return jsonify({
            "status": "success", 
            "summary": summary, 
            "analyzed_count": len(post_ids),
            "result_id": new_result.id,
            "raw_json": ai_result_str,
            "model": selected_model,
            "cost_usd": total_cost,
            "new_balance_usd": new_balance, # 新しい残高をレスポンスに追加
            "usage": usage_data # 使用量（トークン数）も返す
        })

    except Exception as e:
        db.rollback()
        error_msg = f"AI一括分析処理中にエラーが発生しました: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": f"AI analysis failed: {str(e)}", "details": error_msg}), 500
    finally:
        db.close()

# --- APIルート: 投稿の動的絞り込み ---
@app.route('/api/filter-posts', methods=['POST'])
def filter_posts():
    db = SessionLocal()
    try:
        # 1. フロントエンドから検索条件 (JSON) を受け取る
        data = request.get_json()
        
        keyword = data.get('keyword')
        accounts = data.get('accounts', []) # アカウント名のリスト
        likes = data.get('likes')
        rts = data.get('rts')

        # 2. ベースとなるクエリを作成
        #    DB全体を検索対象とする (limit(50) はここではかけない)
        query = db.query(CollectedPost)

        # 3. 条件に応じて動的にフィルタを追加
        if keyword:
            # 大文字/小文字を区別しない (ilike)
            query = query.filter(CollectedPost.original_text.ilike(f"%%{keyword}%%"))
        
        if accounts: # リストが空でない場合
            query = query.filter(CollectedPost.username.in_(accounts))

        if likes is not None:
            try:
                # 文字列で来る可能性も考慮してintに変換
                likes_int = int(likes)
                if likes_int > 0:
                    query = query.filter(CollectedPost.like_count >= likes_int)
            except ValueError:
                pass # 数値変換できなければ無視

        if rts is not None:
            try:
                # 文字列で来る可能性も考慮してintに変換
                rts_int = int(rts)
                if rts_int > 0:
                    query = query.filter(CollectedPost.retweet_count >= rts_int)
            except ValueError:
                pass # 数値変換できなければ無視

        # 4. 絞り込み結果を最新順 (ID降順) で取得
        filtered_posts = query.order_by(CollectedPost.id.desc()).all()

        # 5. 結果をJSONシリアライズ可能な辞書のリストに変換
        results_list = []
        for post in filtered_posts:
            results_list.append({
                "id": post.id,
                "username": post.username,
                # 日時はISO 8601形式の文字列に変換 (JS側でパースするため)
                "posted_at_iso": post.posted_at.isoformat() if post.posted_at else None, 
                "original_text": post.original_text,
                "source_url": post.source_url,
                "like_count": post.like_count,
                "retweet_count": post.retweet_count,
                "link_summary": post.link_summary # 🔗 アイコン表示用
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

# ▼▼▼【ここから追加】▼▼▼
# --- APIルート: 保存済みプロンプト一覧の取得 ---
@app.route('/api/get-prompts', methods=['GET'])
def get_prompts():
    db = SessionLocal()
    try:
        # DBから全てのプロンプトを取得
        prompts = db.query(Prompt).order_by(Prompt.name).all()
        
        # JSONシリアライズ可能な辞書のリストに変換
        results_list = []
        for p in prompts:
            results_list.append({
                "id": p.id,
                "name": p.name,
                "template_text": p.template_text,
                "is_default": p.is_default
            })
        
        # デフォルトプロンプトが1件もなければ、ここで作成する
        if not results_list:
            default_prompt = get_current_prompt(db) # 既存のヘルパー関数を利用
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
# ▲▲▲【ここまで追加】▲▲▲

# ▼▼▼【ここから追加】▼▼▼
# --- APIルート: プロンプトの保存/更新 ---
@app.route('/api/save-prompt', methods=['POST'])
def save_prompt():
    db = SessionLocal()
    try:
        data = request.get_json()
        prompt_id = data.get('promptId')
        prompt_text = data.get('templateText')
        prompt_name = data.get('promptName') # 将来的な「名前を付けて保存」用 (今回は未使用)

        if not prompt_text:
            return jsonify({"status": "error", "message": "プロンプト本文が空です。"}), 400

        # prompt_id が存在すれば「更新」、なければ「新規作成」
        if prompt_id:
            # --- 更新 ---
            prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
            if not prompt:
                return jsonify({"status": "error", "message": "対象のプロンプトが見つかりません。"}), 404
            
            prompt.template_text = prompt_text
            # (もし名前も更新する場合はここで)
            # if prompt_name:
            #     prompt.name = prompt_name
            
            db.commit()
            db.refresh(prompt) # 更新後のデータを取得
            
            return jsonify({
                "status": "success", 
                "message": f"プロンプト '{prompt.name}' を更新しました。",
                "updated_prompt": {
                    "id": prompt.id,
                    "name": prompt.name,
                    "template_text": prompt.template_text,
                    "is_default": prompt.is_default
                }
            })
        
        # ▼▼▼【ここから修正 (新規作成ロジック)】▼▼▼
        else:
            # --- 新規作成 ---
            if not prompt_name:
                return jsonify({"status": "error", "message": "新しいプロンプトの名前を入力してください。"}), 400
            
            # (任意) 同名プロンプトの重複チェック
            existing = db.query(Prompt).filter(Prompt.name == prompt_name).first()
            if existing:
                return jsonify({"status": "error", "message": f"名前 '{prompt_name}' は既に使用されています。"}), 409 # 409 Conflict

            new_prompt = Prompt(
                name = prompt_name,
                template_text = prompt_text,
                is_default = False # 新規作成はデフォルトにはしない
            )
            db.add(new_prompt)
            db.commit()
            db.refresh(new_prompt) # DBが割り当てたIDを取得
            
            return jsonify({
                "status": "success",
                "message": f"プロンプト '{new_prompt.name}' を新規保存しました。",
                "action": "create", # (JS側で判別するため)
                "new_prompt": {
                    "id": new_prompt.id,
                    "name": new_prompt.name,
                    "template_text": new_prompt.template_text,
                    "is_default": new_prompt.is_default
                }
            })
        # ▲▲▲【ここまで修正】▲▲▲

    except Exception as e:
        db.rollback()
        error_msg = f"プロンプト保存中にエラーが発生しました: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": error_msg}), 500
    finally:
        db.close()

# --- APIルート: プロンプトの削除 ---
@app.route('/api/delete-prompt', methods=['POST'])
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
        
        # デフォルトプロンプトは削除させない
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
# ▲▲▲【ここまで追加】▲▲▲

# ▼▼▼【ここから追加】▼▼▼
# --- ページ: 分析履歴一覧 ---
@app.route('/history')
def history():
    db = SessionLocal()
    try:
        # AnalysisResult を取得
        # .options(joinedload(...)) を使い、N+1問題を回避する
        # (N+1問題: ループ内で都度DBに問合せる非効率な処理)
        #
        # 1. prompt (Promptテーブル) と 
        # 2. posts (CollectedPostテーブル) を
        #    最初のクエリで一緒にJOINして読み込む (Eager Loading)
        results = db.query(AnalysisResult).options(
            joinedload(AnalysisResult.prompt),
            joinedload(AnalysisResult.posts)
        ).order_by(AnalysisResult.analyzed_at.desc()).all()
        
        # (次のステップで作成する) history.html に結果を渡す
        return render_template("history.html", results=results)

    except Exception as e:
        print(f"履歴ページの読み込みエラー: {e}")
        flash(f"履歴の読み込みに失敗しました: {e}", "error")
        return redirect(url_for('index')) # エラー時はダッシュボードに戻る
    finally:
        db.close()
# ▲▲▲【ここまで追加】▲▲▲