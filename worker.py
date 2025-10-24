import os
import json
from dotenv import load_dotenv
import tweepy
# import openai ## OPENAI APIはwebappで制御する仕様に変更するため削除
from models import SessionLocal, CollectedPost, Setting
from datetime import datetime, timezone
from dateutil.parser import parse
import time
import requests

# .envファイルから環境変数を読み込む
load_dotenv()

# APIキーと設定の読み込み
X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN")

# OPENAI APIはwebappで制御する仕様に変更するため削除
# OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") 

THREADS_ACCESS_TOKEN = os.environ.get("THREADS_USER_ACCESS_TOKEN")
THREADS_USER_ID = os.environ.get("THREADS_USER_ID")
THREADS_API_BASE_URL = "https://graph.threads.net/v1.0"

# 環境変数からの設定値の読み込みとデフォルト値の設定
try:
    SLEEP_TIME_SECONDS_BETWEEN_POSTS = int(os.environ.get("SLEEP_TIME_SECONDS_BETWEEN_POSTS", "2"))
    SLEEP_TIME_SECONDS_BETWEEN_USER = int(os.environ.get("SLEEP_TIME_SECONDS_BETWEEN_USER", "15"))
except ValueError:
    # もし環境変数が整数に変換できない場合、デフォルト値を使用
    print ("Invalid SLEEP_TIME_SECONDS_BETWEEN_USER value. Using default of 15 seconds.")
    SLEEP_TIME_SECONDS_BETWEEN_POSTS = 2
    SLEEP_TIME_SECONDS_BETWEEN_USER = 15

# X or Threadsが選択された後のタイミングに処理を移動
# if not all([X_BEARER_TOKEN, OPENAI_API_KEY, TARGET_X_USERNAMES_STR]):
#     raise ValueError("必要な環境変数が.envに設定されていません。")

# 監視対象のユーザー名をリストに変換
TARGET_USERNAMES_STR = os.environ.get("TARGET_USERNAMES")
TARGET_USERNAMES = [username.strip() for username in TARGET_USERNAMES_STR.split(",")]

# X or Threadsが選択された後のタイミングに処理を移動
# # APIクライアントの初期化
# client_x = tweepy.Client(X_BEARER_TOKEN)
# client_openai = openai.OpenAI(api_key=OPENAI_API_KEY)

def get_latest_posts_from_x(client_x, username, since_id=None):
    """
    指定されたXユーザー名から最新の投稿を取得する。
    since_idが指定された場合、それ以降の投稿のみを取得する。
    """
    if not client_x:
        print("Error: X API client is not initialized.")
        return False, None

    try:
        user = client_x.get_user(username=username).data
        if not user:
            print(f"Error: User {username} not found.")
            return False, None
        
        # APIにわたすパラメータを動的に設定
        params = {
            "id": user.id,
            "exclude": ["replies", "retweets"],
            "max_results": 100,
            "tweet_fields": ["created_at", "public_metrics"]
        } 
        if since_id:
            params["since_id"] = since_id
        else:
            # since_idがない場合は最新10件のみ取得
            params["max_results"] = 10
        
        response = client_x.get_users_tweets(**params)
        return True, response.data if response.data else []
    except Exception as e:
        print(f"Error fetching posts for {username}: {e}")
        return False, None

def get_latest_posts_from_threads(user_id, since_timestamp=None):
    """
    指定されたThreadsユーザーIDから最新の投稿を取得する。
    since_timestampが指定された場合、それ以降の投稿のみを取得する。
    """
    
    if not THREADS_ACCESS_TOKEN:
        print("Error: THREADS_ACCESS_TOKEN is not set.")
        return False, None
    
    endpoint = f"{THREADS_API_BASE_URL}/{user_id}/threads"

    # APIにわたすパラメータを動的に設定
    params = {
        "access_token": THREADS_ACCESS_TOKEN,
        # 取得したいフィールドを指定
        "fields": "id,media_product_type,text,timestamp,permalink,like_count,reply_count,reshare_count",
        "limit": 25 # 一度に取得するスレッドの数(APIの推奨値)
    }

    
    # since_timestampがある場合は追加
    if since_timestamp:
        params["since"] = since_timestamp

    try:
        # GETリクエストを送信
        response = requests.get(endpoint, params=params)
        response.raise_for_status()  # HTTPエラーが発生した場合に例外をスロー

        # レスポンスのJSONから'data'キーの値を取得
        data = response.json().get("data", [])
        print(f"Fetched {len(data)} threads for user ID {user_id}.")
        return True, data
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching threads for user ID {user_id}: {e}")

        # レスポンス内容を表示（デバッグ用）
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            try:
                print(f"Response content: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response content is not valid JSON: {e.response.text}")
        return False, None

def run_worker():
    db = SessionLocal()
    try:
        # DBからAPI選択設定を取得
        api_provider_setting = db.query(Setting).filter(Setting.key == "api_provider").first()
        API_PROVIER = api_provider_setting.value if api_provider_setting else "X"  # デフォルトは"X"

        print(f"worker sttarted at {datetime.now(timezone.utc).isoformat()} (Provider: {API_PROVIER})")

        target_list = []
        fetch_function = None
        get_since_value = lambda last_post: None
        provider_username_map = {}
        client_x = None # ここで初期化しておく

        # APIプロバイダーに応じた設定
        if API_PROVIER == "X":
            # client_xをここで初期化
            client_x = tweepy.Client(X_BEARER_TOKEN) if X_BEARER_TOKEN else None

            if not client_x or not TARGET_USERNAMES:
                print("X API client or target usernames not properly configured. Skipping X")
                return
            target_list = TARGET_USERNAMES
            fetch_function = get_latest_posts_from_x
            get_since_value = lambda last_post: last_post.post_id if last_post else None
            provider_username_map = {username: username for username in TARGET_USERNAMES}
        
        elif API_PROVIER == "Threads":
            if not THREADS_ACCESS_TOKEN or not THREADS_USER_ID:
                print("Threads API client or user ID not properly configured. Skipping Threads")
                return
            target_list = [THREADS_USER_ID]
            fetch_function = get_latest_posts_from_threads
            get_since_value = lambda last_post: int(last_post.posted_at.timestamp()) if last_post else None
            provider_username_map = {THREADS_USER_ID: "my_threads_account"}  # 任意の名前に変更可能
        else:
            raise ValueError(f"Invalid API_PROVIER setting in database: {API_PROVIER}")

        for target in target_list:
            username_to_process = provider_username_map.get(target)
            print(f"---- Processing user: {target} (as user: {username_to_process}) ----")
        
            latest_post_in_db = db.query(CollectedPost).filter(CollectedPost.username == username_to_process).order_by(CollectedPost.id.desc()).first()
            since_value = get_since_value(latest_post_in_db)

            if API_PROVIER == "X":
                success, raw_posts = fetch_function(client_x, target, since_id=since_value)
            elif API_PROVIER == "Threads":
                success, raw_posts = fetch_function(target, since_value)

            if not success:
                print(f"Failed to fetch posts for user: {target}. Skipping.")
            elif not raw_posts:
                print(f"No new posts found for user: {target}.")
            else:
                print(f"Fetched {len(raw_posts)} new posts for user: {target}.")
                for raw_post in reversed(raw_posts): #古い順に処理
                    normalized_data = normalize_post_data(raw_post, API_PROVIER, username=username_to_process if API_PROVIER == "X" else None)
                    if not normalized_data:
                        print(f"Failed to normalize post data. Skipping.")
                        continue
                        
                    post_id_to_print = normalized_data.get("post_id", "N/A")
                    post_text_preview = normalized_data.get("text", "")[:30]
                    print(f"Processing new post: {post_id_to_print} - {post_text_preview}...")

                    new_collected_post = CollectedPost(
                        username=normalized_data["username"],
                        post_id=normalized_data["post_id"],
                        original_text=normalized_data["text"],
                        # ai_summaryは常にNoneで保存。webappで後処理する仕様に変更
                        ai_summary=None,
                        link_summary=None,
                        source_url=normalized_data["source_url"],
                        posted_at=normalized_data["posted_at"],
                        like_count=normalized_data["like_count"],
                        retweet_count=normalized_data["retweet_count"]
                    )
                    db.add(new_collected_post)
                    db.commit()
                    print(f"Saved post {normalized_data['post_id']} to database.")

                    # 投稿間で少し待つ（API制限回避のため）
                    print(f"Waiting {SLEEP_TIME_SECONDS_BETWEEN_POSTS} seconds before next post...")
                    time.sleep(SLEEP_TIME_SECONDS_BETWEEN_POSTS)

                # ユーザー間で少し待つ（API制限回避のため）
                print(f"Waiting {SLEEP_TIME_SECONDS_BETWEEN_USER} seconds before next user...")
                time.sleep(SLEEP_TIME_SECONDS_BETWEEN_USER)

    except Exception as e:
        print(f"An error occurred during the DB operation: {e}")
        db.rollback()
    finally:
        db.close()
        print("Worker finished.")

def normalize_post_data(raw_post, provider, username=None):
    """
    生の投稿データを正規化して共通のフォーマットに変換する。
    providerは"X"または"Threads"。
    usernameはXの場合に指定。
    """
    try:
        if provider == "X": # Xの場合usernameは必須
            if not username:
                raise ValueError("Username is required for X provider.")
            
            # public_metricsが存在しない場合に備える
            metrics = getattr(raw_post, "public_metrics", {})
            return {
                "username": username,
                "post_id": str(raw_post.id),
                "text": raw_post.text,
                "source_url": f"https://x.com/{username}/status/{raw_post.id}",
                "posted_at": raw_post.created_at,
                "like_count": metrics.get("like_count", 0),
                "retweet_count": metrics.get("retweet_count", 0)
                }
        elif provider == "Threads":
            # ThreadsではusernameはDB保存時に固定値を使用
            username_for_db = "my_threads_account"
            post_id = raw_post.get("id")
            if not post_id:
                raise ValueError("Post ID is missing in Threads data.")
        
            posted_at_str = raw_post.get("timestamp")
            posted_at_dt = parse(posted_at_str) if posted_at_str else None
        if not posted_at_dt: # 投稿日時が無いデータは処理しない
            raise ValueError("Timestamp is missing in Threads data.")
        
        return {
            "username": username_for_db,
            "post_id": post_id,
            "text": raw_post.get("text", ""),
            "source_url": raw_post.get("permalink", ""),
            "posted_at": posted_at_dt,
            "like_count": raw_post.get("like_count", 0),
            "retweet_count":  0 # Threadsにはリツイートに相当する概念がないため0を設定
        }
    except Exception as e:
        # データ構造が予期せぬ形式の場合に備える
        post_id_for_log = getattr(raw_post, "id", raw_post.get("id", "N/A"))
        print(f"Error normalizing post data (Post ID: {post_id_for_log}): {e}")
        return None # 正規化に失敗した場合はNoneを返し、呼び出し元でスキップさせる
    
    #ここに到達した場合も異常なのでNoneを返す
    return None

if __name__ == "__main__":
    run_worker()