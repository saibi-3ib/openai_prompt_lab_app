import os
import json
import requests # API呼び出しのため追加
from flask import Flask, render_template, request, redirect, url_for, jsonify
from models import SessionLocal, CollectedPost, Setting, Prompt, AnalysisResult # 新しいモデルをインポート
from datetime import datetime, timezone
import openai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- 設定値と初期化 ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client_openai = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
# プロンプト編集機能のための初期プロンプト名
DEFAULT_PROMPT_KEY = "default_summary"


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

# --- メインページ (データ表示) ---
@app.route('/')
def index():
    db = SessionLocal()
    try:
        posts = db.query(CollectedPost).order_by(CollectedPost.id.desc()).limit(50).all()
        # API設定を読み込み
        current_provider = get_current_provider(db)
        
        return render_template("index.html", posts=posts, current_provider=current_provider)
    finally:
        db.close()

# --- 設定管理ページ (API切り替え、プロンプト編集) ---
@app.route('/manage', methods=['GET', 'POST'])
def manage():
    db = SessionLocal()
    try:
        # POST処理: APIプロバイダーの切り替え
        if request.method == 'POST':
            action = request.form.get('action') # 追加: どのアクションか識別
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
                    print(f"debug: commit successful for provider {provider}")  # デバッグ用ログ
                else:
                    print(f"Invalid provider selected: {provider}")  # デバッグ用ログ

            # 2. プロンプトの編集処理
            elif action == 'save_prompt':
                prompt_text = request.form.get('prompt_text')

                if prompt_text:
                    prompt = db.query(Prompt).filter(Prompt.name == DEFAULT_PROMPT_KEY).first()
                    if prompt:
                        prompt.template_text = prompt_text
                        db.commit()
                        print(f"debug: commit successful for provider {prompt}")  # デバッグ用ログ
                        

            return redirect(url_for('manage')) # 処理後にリダイレクト

        # GET処理: ページ表示
        current_provider = get_current_provider(db)
        current_prompt = get_current_prompt(db)
        
        return render_template("manage.html", 
                               current_provider=current_provider, 
                               default_prompt=current_prompt.template_text)
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
            model=ANALYSIS_MODEL, # 固定したモデル名を使用            
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

        # コスト計算
        total_cost = calculate_cost(ANALYSIS_MODEL, usage_data)

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
            # ▼▼▼【修正点5】コスト情報をレスポンスに追加 ▼▼▼
            "model": ANALYSIS_MODEL,
            "cost_usd": total_cost,
            "usage": usage_data # 使用量（トークン数）も返す
        })

    except Exception as e:
        db.rollback()
        error_msg = f"AI一括分析処理中にエラーが発生しました: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": f"AI analysis failed: {str(e)}", "details": error_msg}), 500
    finally:
        db.close()