import os
import json
from dotenv import load_dotenv
import tweepy
import openai
from models import SessionLocal, CollectedPost
from datetime import datetime, timezone

# .envファイルから環境変数を読み込む
load_dotenv()

# APIキーと設定の読み込み
X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
TARGET_X_USERNAMES_STR = os.environ.get("TARGET_X_USERNAMES")

if not all([X_BEARER_TOKEN, OPENAI_API_KEY, TARGET_X_USERNAMES_STR]):
    raise ValueError("必要な環境変数が.envに設定されていません。")

# カンマ区切りのユーザー名をリストに変換
TARGET_X_USERNAMES = [username.strip() for username in TARGET_X_USERNAMES_STR.split(",")]

# APIクライアントの初期化
client_x = tweepy.Client(X_BEARER_TOKEN)
client_openai = openai.OpenAI(api_key=OPENAI_API_KEY)

def get_latest_posts(username, since_id=None):
    """
    指定されたXユーザー名から最新の投稿を取得する。
    since_idが指定された場合、それ以降の投稿のみを取得する。
    """
    try:
        user = client_x.get_user(username=username).data
        if not user:
            print(f"Error: User {username} not found.")
            return []
        
        # APIにわたすパラメータを動的に設定
        params = {
            "id": user.id,
            "exclude": ["replies", "retweets"],
            "max_results": 100
        } 
        if since_id:
            params["since_id"] = since_id
        else:
            # since_idがない場合は最新10件のみ取得
            params["max_results"] = 10
        
        response = client_x.get_users_tweets(**params)
        return response.data if response.data else []
    except Exception as e:
        print(f"Error fetching posts for {username}: {e}")
        return []

def process_with_openai(text):
    """
    OpenAI APIを使用してテキストを処理する。
    """
    try:
        prompt = f"""
        以下の英語の文章を日本語に翻訳し、投資家向けの視点で最も重要なポイントを1つの短い文で要約してください。

        結果は必ず以下のJSON形式で返してください。
        {{
          "translation": "ここに翻訳結果",
          "summary": "ここに要約結果"
        }}

        原文:
        {text}
        """

        response = client_openai.chat.completions.create(
            model="gpt-3.5-turbo",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                {"role": "user", "content": prompt}
            ]
        )
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        print(f"Error processing text with OpenAI: {e}")
        return None

def run_worker():
    print(f"Cron Job started at {datetime.now(timezone.utc).isoformat()}")

    db = SessionLocal()
    try:
        for username in TARGET_X_USERNAMES:
            print(f"---- Processing user: {username} ----")

            #1. DBからこのユーザーの最新の投稿IDを取得
            latest_post_in_db = db.query(CollectedPost).filter(CollectedPost.username == username).order_by(CollectedPost.id.desc()).first()
            since_id = latest_post_in_db.post_id if latest_post_in_db else None

            #2. since_idを使って最新の投稿のみを取得
            new_posts = get_latest_posts(username, since_id=since_id)

            if not new_posts:
                print(f"No new posts found for user: {username}")
                continue

            #取得したポストはすべて新しいのでDB存在チェックは不要
            for post in reversed(new_posts):
                print(f"Processing new post: {post.id} - {post.text[:30]}...")
            
                ai_result_str = process_with_openai(post.text)
                if not ai_result_str:
                    print(f"Failed to process post {post.id} with OpenAI. Skipping.")
                    continue
            
                try:
                    ai_result_json = json.loads(ai_result_str)
                    summary = ai_result_json.get("summary", "Summary not available.")
                except json.JSONDecodeError:
                    print(f"Failed to parse OpenAI response for post {post.id}. Skipping.")
                    continue

                #3. DBに保存。保存時にusernameも保存する
                new_collected_post = CollectedPost(
                    username=username,
                    post_id=str(post.id),
                    original_text=post.text,
                    processed_data=summary,
                    source_url=f"https://x.com/{username}/status/{post.id}"
                )
                db.add(new_collected_post)
                db.commit()
                print(f"Saved post {post.id} to database.")
            
    except Exception as e:
        print(f"An error occurred during the DB operation: {e}")
        db.rollback()
    finally:
        db.close()
        print("Cron Job finished.")

if __name__ == "__main__":
    run_worker()