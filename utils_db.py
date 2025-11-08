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
    """DB から現在選択されているプロンプトを返す。
    優先順位:
    1) Setting.key == 'default_prompt_name' の値（Prompt.name）
    2) DEFAULT_PROMPT_KEY（既存のフォールバック）
    3) 存在しなければ DEFAULT_PROMPT_KEY 名で新規作成して返す
    """
    # 1) 設定に default_prompt_name があるか確認
    default_setting = db.query(Setting).filter(Setting.key == 'default_prompt_name').first()
    prompt = None
    if default_setting and default_setting.value:
        prompt = db.query(Prompt).filter(Prompt.name == default_setting.value).first()

    # 2) 設定がなければ、従来の DEFAULT_PROMPT_KEY を使う
    if not prompt:
        prompt = db.query(Prompt).filter(Prompt.name == DEFAULT_PROMPT_KEY).first()

    # 3) それでもなければ従来どおり初期プロンプトを作成して返す
    if not prompt:
        default_text = """
                        You are a data-extraction engine. Given the text block(s) in {texts} and the ticker context in {ticker_context}, output exactly one JSON object (no extra text) with this schema:

                        {
                        "overall_summary": "<短く投資家向けの概要（日本語）>",
                        "detailed_analysis": [
                            {
                            "post_db_id": <整数: POST_DB_ID from the provided texts>,
                            "ticker_sentiments": [
                                { "ticker": "<ティッカー記号>", "sentiment": "Positive"|"Negative"|"Neutral", "reason": "<短い理由（日本語）>" }
                            ]
                            }
                        ]
                        }
                        """
        new_prompt = Prompt(name=DEFAULT_PROMPT_KEY, template_text=default_text, is_default=True)
        db.add(new_prompt)
        db.commit()
        db.refresh(new_prompt)
        prompt = new_prompt

    return prompt

# --- (リファクタリング) 一括分析のビジネスロジック ---

def _run_analysis_logic(
    db: Session,
    posts_to_analyze: List[CollectedPost], # (★) IDリストではなく、投稿オブジェクトのリストを受け取る
    prompt_text: str, 
    selected_model: str,
    selected_prompt_name: str,
    ticker_context_map: Dict # (★) S&P500の辞書も外から受け取る
) -> Dict:
    """
    AI分析のコアロジック。
    セッション(db)を引数として受け取り、コミットは行わない。
    Web (run_batch_analysis) と Worker (worker.py) から共有される。
    """
    
    # --- 1. S&P500の辞書を構築 ---
    # (注: ticker_context_map は呼び出し元で取得済みの前提)
    ticker_context = "--- Stock Ticker Context (Ticker: Company Name [Sector]) ---\n"
    for item in ticker_context_map:
        sector_info = f" [{item.gics_sector or 'N/A'}]"
        ticker_context += f"{item.ticker}: {item.company_name}{sector_info}\n"
    ticker_context += "-------------------------------------------------------\n\n"

    # --- 2. 分析対象の投稿データ (引数で受け取り済み) ---
    posts = posts_to_analyze
    if not posts:
        raise Exception("分析対象の投稿データが見つかりませんでした。")

    # --- 3. (要件) 投稿から「監視対象アカウントID」を取得または作成 ---
    first_post = posts[0]
    username_to_process = first_post.username
    target_account = db.query(TargetAccount).filter(TargetAccount.username == username_to_process).first()
    if not target_account:
        target_account = TargetAccount(
            username=username_to_process,
            is_active=True, # (★) workerからの自動登録時はTrue
            added_at=datetime.now(timezone.utc)
        )
        db.add(target_account)
        db.flush() 
    account_id_to_update = target_account.id

    # --- 4. (親) AnalysisResult を *先に* 作成 ---
    current_prompt = db.query(Prompt).filter(Prompt.name == selected_prompt_name).first()
    new_result = AnalysisResult(
        prompt_id = current_prompt.id if current_prompt else 1,
        ai_model = selected_model,
        raw_json_response = "Aggregated results (see TickerSentiment table)",
        extracted_summary = "Aggregated results"
    )
    for post in posts:
        new_result.posts.append(post)
    db.add(new_result)
    db.flush()

    # --- 5. (★重要★) 投稿ごとにAIを呼び出すループ ---
    total_input_tokens = 0
    total_output_tokens = 0
    all_summaries = []
    ticker_mention_counts = {}

    for post in posts:
        try:
            print(f"--- Analyzing Post DB ID: {post.id} ---")
            
            # (a) 1件の投稿のみでプロンプトを構築
            combined_texts = "--- Post to Analyze ---\n"
            combined_texts += f"POST_DB_ID: {post.id}\n"
            combined_texts += f"TEXT: {post.original_text}\n"
            combined_texts += "---\n"
            
            full_prompt = prompt_text.replace("{texts}", combined_texts)
            full_prompt = full_prompt.replace("{ticker_context}", ticker_context)

            # (b) AI呼び出し (1件ごと)
            response = client_openai.chat.completions.create(
                model=selected_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are a data extraction engine designed to output JSON."},
                    {"role": "user", "content": full_prompt}
                ]
            )
            ai_result_str = response.choices[0].message.content
            usage_data = response.usage.model_dump()
            
            # (c) トークンとコストを集計
            total_input_tokens += usage_data.get("prompt_tokens", 0)
            total_output_tokens += usage_data.get("completion_tokens", 0)
            
            # (d) AI応答(JSON)をパース
            ai_result_json = json.loads(ai_result_str)
            all_summaries.append(ai_result_json.get("overall_summary", ""))

            # (e) センチメント/言及回数の処理
            detailed_analysis = ai_result_json.get("detailed_analysis", [])
            for post_analysis in detailed_analysis:
                if post_analysis.get("post_db_id") != post.id:
                    print(f"Warning: AI returned wrong post_db_id. Expected {post.id}, got {post_analysis.get('post_db_id')}")
                    continue

                ticker_sentiments = post_analysis.get("ticker_sentiments", [])
                for sentiment_data in ticker_sentiments:
                    ticker = sentiment_data.get("ticker")
                    if not (ticker and sentiment_data.get("sentiment")):
                        continue
                    
                    # (処理 1) TickerSentiment (ログ) に保存
                    new_log = TickerSentiment(
                        analysis_result_id = new_result.id, # 親ID
                        collected_post_id = post.id,
                        ticker = ticker,
                        sentiment = sentiment_data.get("sentiment"),
                        reasoning = sentiment_data.get("reason", "")
                    )
                    db.add(new_log)

                    # (処理 2) Pythonの辞書で「言及回数」をカウントアップ
                    ticker_mention_counts[ticker] = ticker_mention_counts.get(ticker, 0) + 1
        
        except Exception as e:
            print(f"!!!!!!!! ERROR processing Post DB ID {post.id}: {e} !!!!!!!!")
            print("Continuing to next post...")

    # --- 6. (★重要★) ループ完了後、DBの重み付けを更新 ---
    existing_weights = db.query(UserTickerWeight).filter(
        UserTickerWeight.account_id == account_id_to_update,
        UserTickerWeight.ticker.in_(ticker_mention_counts.keys())
    ).all()
    weight_map = {record.ticker: record for record in existing_weights}
    
    for ticker, count in ticker_mention_counts.items():
        if ticker in weight_map:
            weight_record = weight_map[ticker]
            weight_record.total_mentions += count
            weight_record.last_analyzed_at = datetime.now(timezone.utc)
        else:
            new_weight_record = UserTickerWeight(
                account_id = account_id_to_update,
                ticker = ticker,
                total_mentions = count,
                weight_ratio = 0.0,
                last_analyzed_at = datetime.now(timezone.utc)
            )
            db.add(new_weight_record)

    # --- 7. (親) AnalysisResult を集計値で更新 ---
    total_cost = calculate_cost(selected_model, {
        "prompt_tokens": total_input_tokens,
        "completion_tokens": total_output_tokens
    })
    new_balance = update_credit_balance(db, total_cost)
    
    new_result.input_tokens = total_input_tokens
    new_result.output_tokens = total_output_tokens
    new_result.cost_usd = total_cost
    new_result.extracted_summary = " | ".join(all_summaries)
    new_result.raw_json_response = f"Aggregated {len(posts)} posts. See TickerSentiment table for details."
    new_result.analyzed_at = datetime.now(timezone.utc)

    # (★) db.commit() は *しない*
    
    # --- 9. 成功レスポンスを返す ---
    # (Web UI と Worker 共通で使う戻り値)
    return {
        "status": "success", 
        "summary": new_result.extracted_summary,
        "analyzed_count": len(posts),
        "result_id": new_result.id,
        "raw_json": new_result.raw_json_response,
        "model": selected_model,
        "cost_usd": total_cost,
        "new_balance_usd": new_balance,
        "usage": {
            "prompt_tokens": total_input_tokens,
            "completion_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens
        }
    }


def run_batch_analysis(
    post_ids: List[int], 
    prompt_text: str, 
    selected_model: str,
    selected_prompt_name: str
) -> Dict:
    """
    Web UI (app.py) から呼び出されるラッパー関数。
    セッションを管理し、コアロジックを呼び出し、コミットする。
    """
    
    if not client_openai:
        raise Exception("OpenAI API Key not configured.")
    if not post_ids or not prompt_text:
        raise Exception("投稿IDのリストとプロンプトテキストが必要です。")

    db = SessionLocal()
    try:
        # (★) S&P500辞書と投稿データを *先に* 取得する
        ticker_maps = db.query(StockTickerMap).all()
        posts = db.query(CollectedPost).filter(CollectedPost.id.in_(post_ids)).all()
        if not posts:
            raise Exception("選択された投稿IDに対応するデータが見つかりませんでした。")
        
        # (★) コアロジックを呼び出す
        result_data = _run_analysis_logic(
            db = db,
            posts_to_analyze = posts,
            prompt_text = prompt_text,
            selected_model = selected_model,
            selected_prompt_name = selected_prompt_name,
            ticker_context_map = ticker_maps
        )
        
        # (★) コミット
        db.commit()
        
        return result_data

    except Exception as e:
        db.rollback()
        raise e 
    finally:
        db.close()
