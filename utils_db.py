import os
import json
import openai
from models import SessionLocal, CollectedPost, Setting, Prompt, AnalysisResult
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from models import (
    SessionLocal, CollectedPost, Setting, Prompt, AnalysisResult, 
    TargetAccount, StockTickerMap, TickerSentiment, UserTickerWeight
)

# --- 設定値と初期化 ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client_openai = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
DEFAULT_PROMPT_KEY = "default_summary"

# 選択可能なOpenAIモデル
AVAILABLE_MODELS = ["gpt-4o-mini", "gpt-3.5-turbo", "gpt-4o"]

# --- OpenAI コスト計算定数と関数 ---
COST_PER_MILLION = {
    "gpt-4o": {"input": 5.00, "output": 15.00},          # <-- ▼▼▼【これを追加】▼▼▼
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}

def calculate_cost(model_name: str, usage: dict) -> float:
    """トークン使用量から概算コスト (USD) を計算する"""
    if model_name not in COST_PER_MILLION:
        print(f"Warning: Cost data for model {model_name} is missing.")
        return 0.0

    input_cost = COST_PER_MILLION[model_name]["input"]
    output_cost = COST_PER_MILLION[model_name]["output"]

    total_cost = (usage.get("prompt_tokens", 0) / 1_000_000) * input_cost + \
                 (usage.get("completion_tokens", 0) / 1_000_000) * output_cost
    
    return round(total_cost, 8)

def update_credit_balance(db: Session, cost_usd: float) -> float:
    """残高から消費コストを差し引き、DBを更新する (コミットは呼び出し元)"""
    setting = db.query(Setting).filter(Setting.key == 'openai_total_credit').first()
    if not setting:
        return 0.0

    try:
        current_balance = float(setting.value)
        new_balance = current_balance - cost_usd
        setting.value = str(round(new_balance, 8))
        return new_balance
    except ValueError as e:
        print(f"Error updating credit balance: {e}")
        return current_balance

def get_or_create_credit_setting(db: Session, initial_value='20.000000') -> Setting:
    """DBからOpenAIクレジット設定を取得。なければ初期値で作成し、そのSettingオブジェクトを返す。"""
    key = 'openai_total_credit'
    setting = db.query(Setting).filter(Setting.key == key).first()
    
    if not setting:
        new_setting = Setting(key=key, value=initial_value)
        db.add(new_setting)
        db.commit() # (初回作成時のみ例外的にコミット)
        return new_setting
    return setting

# --- DB操作ヘルパー関数 ---
def get_current_provider(db: Session) -> str:
    """DBから現在のAPIプロバイダー設定を取得する"""
    setting = db.query(Setting).filter(Setting.key == 'api_provider').first()
    return setting.value if setting else 'X'

def get_current_prompt(db: Session) -> Prompt:
    """DBからデフォルトのプロンプトを取得する。なければ初期値を作成する。"""
    prompt = db.query(Prompt).filter(Prompt.name == DEFAULT_PROMPT_KEY).first()
    if not prompt:
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
        db.commit() # (初回作成時のみ例外的にコミット)
        return new_prompt
    return prompt

# --- (リファクタリング) 一括分析のビジネスロジック ---
def run_batch_analysis(
    post_ids: List[int], 
    prompt_text: str, 
    selected_model: str,
    selected_prompt_name: str
) -> Dict:
    """
    一括分析の実行（DB接続、AIコール、DB保存）を行い、
    JSONレスポンス用の辞書を返す。
    (S&P500/センチメント/言及回数カウントアップ対応版)
    """
    if not client_openai:
        raise Exception("OpenAI API Key not configured.")
    if not post_ids or not prompt_text:
        raise Exception("投稿IDのリストとプロンプトテキストが必要です。")

    db = SessionLocal()
    try:
        # --- 1. 分析対象の投稿データを取得 ---
        posts = db.query(CollectedPost).filter(CollectedPost.id.in_(post_ids)).all()
        if not posts:
            raise Exception("選択された投稿IDに対応するデータが見つかりませんでした。")

        # --- 2. (要件) 投稿から「監視対象アカウントID」を取得 ---
        # (注: 要件に基づき、バッチ処理は単一アカウントの投稿のみと仮定)
        first_post = posts[0]
        target_account = db.query(TargetAccount).filter(TargetAccount.username == first_post.username).first()
        
        if not target_account:
            raise Exception(f"監視対象アカウント '{first_post.username}' が 'target_accounts' テーブルに登録されていません。")
        
        account_id_to_update = target_account.id

        # --- 3. (要件) S&P500の辞書をDBから取得し、AIコンテキストを生成 ---
        ticker_maps = db.query(StockTickerMap).all()
        ticker_context = "--- 対象銘柄コンテキスト (ティッカー: 企業名, 愛称) ---\n"
        for item in ticker_maps:
            aliases = f", {item.aliases}" if item.aliases else ""
            ticker_context += f"{item.ticker}: {item.company_name}{aliases}\n"
        ticker_context += "-----------------------------------------------\n\n"
        
        # --- 4. (要件) AIに渡す投稿テキストとプロンプトを構築 ---
        # (AIが投稿DB IDを特定できるよう、IDも渡す)
        combined_texts = "--- 分析対象の投稿リスト ---\n"
        for post in posts:
            combined_texts += f"POST_DB_ID: {post.id}\n"
            combined_texts += f"TEXT: {post.original_text}\n"
            combined_texts += "---\n"

        # プロンプトのプレースホルダーを置換
        full_prompt = prompt_text.replace("{texts}", combined_texts)
        full_prompt = full_prompt.replace("{ticker_context}", ticker_context)
        
        # (フォールバック)
        full_prompt = full_prompt.replace("{text}", "[警告: {text} 変数は単数分析用です。{texts} を使用してください。]")


        # --- 5. AI呼び出し ---
        response = client_openai.chat.completions.create(
            model=selected_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                {"role": "user", "content": full_prompt}
            ]
        )
        ai_result_str = response.choices[0].message.content
        usage_data = response.usage.model_dump()

        # --- 6. 結果のパースとコスト計算 ---
        ai_result_json = json.loads(ai_result_str)
        
        # (a) 全体サマリー (AnalysisResult用)
        summary = ai_result_json.get("overall_summary", "Summary not available.")
        
        # (b) コスト計算と残高更新
        total_cost = calculate_cost(selected_model, usage_data)
        new_balance = update_credit_balance(db, total_cost)

        # --- 7. DBに保存 (AnalysisResult - 親ログ) ---
        current_prompt = db.query(Prompt).filter(Prompt.name == selected_prompt_name).first()
        
        new_result = AnalysisResult(
            prompt_id = current_prompt.id if current_prompt else 1, 
            raw_json_response = ai_result_str, 
            extracted_summary = summary,
            ai_model = selected_model,
            cost_usd = total_cost,
            input_tokens = usage_data.get("prompt_tokens", 0),
            output_tokens = usage_data.get("completion_tokens", 0),
            # (注: extracted_tickers は TickerSentiment に移行したため、ここは null のまま)
        )
        # この分析がどの投稿を使ったかを紐付ける (多対多)
        for post in posts:
            new_result.posts.append(post)
        
        db.add(new_result)
        db.flush() # new_result.id を確定させる (TickerSentiment で参照するため)

        # --- 8. (要件) 詳細なセンチメント/言及回数の処理 ---
        detailed_analysis = ai_result_json.get("detailed_analysis", [])

        for post_analysis in detailed_analysis:
            post_db_id = post_analysis.get("post_db_id")
            ticker_sentiments = post_analysis.get("ticker_sentiments", [])

            for sentiment_data in ticker_sentiments:
                ticker = sentiment_data.get("ticker")
                sentiment = sentiment_data.get("sentiment") # "Positive", "Negative", "Neutral"
                reasoning = sentiment_data.get("reason", "")

                if not (post_db_id and ticker and sentiment):
                    print(f"Skipping invalid sentiment data: {sentiment_data}")
                    continue 

                # (処理 1) TickerSentiment (ログ) に保存
                new_log = TickerSentiment(
                    analysis_result_id = new_result.id,
                    collected_post_id = post_db_id,
                    ticker = ticker,
                    sentiment = sentiment,
                    reasoning = reasoning
                )
                db.add(new_log)

                # (処理 2) UserTickerWeight (集計) を更新
                # (既存の集計行を検索 (なければ作成))
                weight_record = db.query(UserTickerWeight).filter_by(
                    account_id = account_id_to_update,
                    ticker = ticker
                ).first()
                
                if not weight_record:
                    weight_record = UserTickerWeight(
                        account_id = account_id_to_update,
                        ticker = ticker,
                        total_mentions = 0, # (初期値)
                        weight_ratio = 0.0  # (初期値)
                    )
                    db.add(weight_record)
                
                # ★要件: 「言及回数」を+1する (ポジ/ネガ問わず)
                weight_record.total_mentions += 1
                weight_record.last_analyzed_at = datetime.now(timezone.utc)
                
                # (注: weight_ratio の計算は、分離された 'calculate_weights.py' バッチで行う)
        
        # --- 9. コミット ---
        db.commit()
        
        # --- 10. 成功レスポンスを返す ---
        return {
            "status": "success", 
            "summary": summary, 
            "analyzed_count": len(post_ids),
            "result_id": new_result.id,
            "raw_json": ai_result_str,
            "model": selected_model,
            "cost_usd": total_cost,
            "new_balance_usd": new_balance,
            "usage": usage_data
        }

    except Exception as e:
        db.rollback()
        # エラーを再度スローし、呼び出し元 (app.py) でキャッチさせる
        raise e 
    finally:
        db.close()