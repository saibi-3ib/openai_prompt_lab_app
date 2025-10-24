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