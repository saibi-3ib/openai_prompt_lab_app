import os
import json
import openai
from models import SessionLocal, CollectedPost, Setting, Prompt, AnalysisResult
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

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
    selected_model: str
) -> Dict:
    """
    一括分析の実行（DB接続、AIコール、DB保存）を行い、
    JSONレスポンス用の辞書を返す。
    """
    if not client_openai:
        raise Exception("OpenAI API Key not configured.")
    if not post_ids or not prompt_text:
        raise Exception("投稿IDのリストとプロンプトテキストが必要です。")

    db = SessionLocal()
    try:
        posts = db.query(CollectedPost).filter(CollectedPost.id.in_(post_ids)).all()
        if not posts:
            raise Exception("選択された投稿IDに対応するデータが見つかりませんでした。")

        combined_texts = ""
        for i, post in enumerate(posts):
            combined_texts += f"--- POST {i+1} (ID:{post.post_id}) ---\n"
            combined_texts += post.original_text + "\n\n"
        
        full_prompt = prompt_text.replace("{texts}", combined_texts)
        full_prompt = full_prompt.replace("{text}", "[警告: {text} 変数は単数分析用です。{texts} を使用してください。]")

        # AI呼び出し
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

        # 結果のパース
        ai_result_json = json.loads(ai_result_str)
        
        # ▼▼▼【ここを修正】▼▼▼
        # 複数のキーを試行してサマリーを抽出 (overall_summary を最優先)
        summary = ai_result_json.get("overall_summary", None) # (1) Comprehensive_v2 形式
        if summary is None:
            summary = ai_result_json.get("analysis_summary", None) # (2) Sentiment_v1 形式
        if summary is None:
            summary = ai_result_json.get("summary", "Summary not available.") # (3) default_summary 形式
        # ▲▲▲【修正ここまで】▲▲▲
        
        # コスト計算と残高更新
        total_cost = calculate_cost(selected_model, usage_data)
        new_balance = update_credit_balance(db, total_cost)

        # DBに保存
        current_prompt = db.query(Prompt).filter(Prompt.name == DEFAULT_PROMPT_KEY).first()
        new_result = AnalysisResult(
            prompt_id = current_prompt.id if current_prompt else 1, 
            raw_json_response = ai_result_str, 
            extracted_summary = summary,
            ai_model = selected_model,
            cost_usd = total_cost            
        )
        for post in posts:
            new_result.posts.append(post)
        
        db.add(new_result)
        db.commit()
        
        # 成功レスポンスを返す
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