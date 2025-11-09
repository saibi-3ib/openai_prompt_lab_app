import os
import json
from dotenv import load_dotenv
# import tweepy # (★) tweepy は使わない
from models import SessionLocal, CollectedPost, Setting, StockTickerMap, Prompt, TargetAccount
from datetime import datetime, timezone
from dateutil.parser import parse
import time
import requests
from sqlalchemy.exc import IntegrityError
from requests_oauthlib import OAuth1Session
from utils_db import _run_analysis_logic, AVAILABLE_MODELS, client_openai, DEFAULT_PROMPT_KEY, get_current_prompt

load_dotenv()

# APIキーと設定の読み込み
X_API_KEY = os.environ.get("X_API_KEY")
X_API_KEY_SECRET = os.environ.get("X_API_KEY_SECRET")
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET")

THREADS_ACCESS_TOKEN = os.environ.get("THREADS_USER_ACCESS_TOKEN")
THREADS_USER_ID = os.environ.get("THREADS_USER_ID")
THREADS_API_BASE_URL = "https://graph.threads.net/v1.0"

try:
    SLEEP_TIME_SECONDS_BETWEEN_POSTS = int(os.environ.get("SLEEP_TIME_SECONDS_BETWEEN_POSTS", "2"))
    SLEEP_TIME_SECONDS_BETWEEN_USER = int(os.environ.get("SLEEP_TIME_SECONDS_BETWEEN_USER", "15"))
except ValueError:
    print ("Invalid SLEEP_TIME_SECONDS_BETWEEN_USER value. Using default of 15 seconds.")
    SLEEP_TIME_SECONDS_BETWEEN_POSTS = 2
    SLEEP_TIME_SECONDS_BETWEEN_USER = 15


# ▼▼▼【ここから変更】tweepy.Client の代わりに OAuth1Session を使う ▼▼▼

def _make_oauth1_session():
    """OAuth1.1aセッションを .env キーから作成する"""
    consumer_key = X_API_KEY.strip() if X_API_KEY else None
    consumer_secret = X_API_KEY_SECRET.strip() if X_API_KEY_SECRET else None
    access_token = X_ACCESS_TOKEN.strip() if X_ACCESS_TOKEN else None
    access_secret = X_ACCESS_TOKEN_SECRET.strip() if X_ACCESS_TOKEN_SECRET else None

    if not all([consumer_key, consumer_secret, access_token, access_secret]):
        return None
    return OAuth1Session(client_key=consumer_key,
                         client_secret=consumer_secret,
                         resource_owner_key=access_token,
                         resource_owner_secret=access_secret)

def get_latest_posts_from_x(oauth_session, username, since_id=None):
    """
    指定されたXユーザー名から最新の投稿を取得する (requests_oauthlib を使用)
    """
    if not oauth_session:
        print("Error: OAuth1Session is not initialized.")
        return False, None

    try:
        # 1. ユーザー名からユーザーIDを取得
        url_user = f"https://api.twitter.com/2/users/by/username/{username}"
        r_user = oauth_session.get(url_user)
        r_user.raise_for_status()
        user_json = r_user.json()
        user_id = user_json.get("data", {}).get("id")
        
        if not user_id:
            print(f"Error: User {username} not found via v2 API.")
            return False, None
        
        # 2. ユーザーIDからツイートを取得
        url_tweets = f"https://api.twitter.com/2/users/{user_id}/tweets"
        params = {
            "exclude": "replies,retweets",
            "max_results": 100,
            "tweet.fields": "created_at,public_metrics"
        } 
        if since_id:
            params["since_id"] = since_id
        else:
            params["max_results"] = 10 # (★) 初回取得は10件
        
        r_tweets = oauth_session.get(url_tweets, params=params)
        r_tweets.raise_for_status()
        tweets_json = r_tweets.json()
        
        return True, tweets_json.get("data", [])
        
    except Exception as e:
        print(f"Error fetching posts for {username} via OAuth1Session: {e}")
        return False, None

# (★) search_recent_posts_from_user 関数は不要なので削除
# def search_recent_posts_from_user(...):

# (★) get_latest_posts_from_threads 関数は変更なし
def get_latest_posts_from_threads(user_id, since_timestamp=None):
    # ... (Threads のコードはそのまま) ...
    if not THREADS_ACCESS_TOKEN:
        print("Error: THREADS_ACCESS_TOKEN is not set.")
        return False, None
    
    endpoint = f"{THREADS_API_BASE_URL}/{user_id}/threads"
    params = {
        "access_token": THREADS_ACCESS_TOKEN,
        "fields": "id,text,timestamp,permalink,like_count,reshare_count",
        "limit": 25
    }
        
    try:
        response = requests.get(endpoint, params=params)
        response.raise_for_status()
        raw_posts = response.json().get("data", [])
        print(f"Fetched {len(raw_posts)} threads for user ID {user_id}.")

        if since_timestamp:
            filter_dt = datetime.fromtimestamp(since_timestamp, tz=timezone.utc)
            filtered_posts = []
            for post in raw_posts:
                post_timestamp_str = post.get("timestamp")
                if post_timestamp_str:
                    try:
                        post_dt = parse(post_timestamp_str)
                        if post_dt > filter_dt:
                            filtered_posts.append(post)
                    except ValueError:
                        print(f"Warning: Invalid timestamp format in post ID {post.get('id','N/A')}: {post_timestamp_str}")
            print(f"Filtered {len(raw_posts) - len(filtered_posts)} posts older than since_timestamp.")
            return True, filtered_posts
        
        return True, raw_posts
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching threads for user ID {user_id}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            try:
                print(f"Response content: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response content: {e.response.text}")
        return False, None
# ▲▲▲【変更ここまで】▲▲▲

def run_worker():
    db = SessionLocal()
    try:
        # DBからAPI選択設定を取得
        api_provider_setting = db.query(Setting).filter(Setting.key == "api_provider").first()
        API_PROVIER = api_provider_setting.value if api_provider_setting else "X"

        print(f"worker sttarted at {datetime.now(timezone.utc).isoformat()} (Provider: {API_PROVIER})")

        # --- AI分析の準備 (変更なし) ---
        run_ai_analysis = True 
        if not client_openai:
            print("OpenAI API Key not configured. Worker can only collect posts, not analyze them.")
            run_ai_analysis = False
        else:
            try:
                ticker_maps = db.query(StockTickerMap).all()
                current_prompt_obj = get_current_prompt(db)
                if not current_prompt_obj:
                    raise Exception("現在選択されているプロンプトが取得できません。")
                prompt_template_text = current_prompt_obj.template_text
                prompt_name_to_use = current_prompt_obj.name

                ai_model_to_use = "gpt-4o-mini" 
                if ai_model_to_use not in AVAILABLE_MODELS:
                    ai_model_to_use = AVAILABLE_MODELS[0]
                
                print(f"AI Analysis is READY. Using model: {ai_model_to_use} and prompt: {prompt_name_to_use}")
                run_ai_analysis = True

            except Exception as e:
                print(f"AI分析の準備に失敗しました: {e}")
                print("Workerは分析を実行せず、投稿収集のみ行います。")
                run_ai_analysis = False


        target_list = []
        fetch_function = None
        get_since_value = lambda last_post: None
        provider_username_map = {}
        
        # ▼▼▼【ここから変更】tweepy.Client の代わりに OAuth1Session を使う ▼▼▼
        oauth_session = None # (★) client_x の代わりに oauth_session

        if API_PROVIER == "X":
            oauth_session = _make_oauth1_session() # (★) ヘルパー関数を呼び出す
            
            if not oauth_session:
                print("X API OAuth 1.1a keys not fully configured in .env. Skipping X.")
                return

            # (★) DBから監視対象アカウントを取得 (provider='X' で絞り込む)
            active_accounts = db.query(TargetAccount).filter(
                TargetAccount.is_active == True,
                TargetAccount.provider == API_PROVIER
            ).all()
            target_list = [acc.username for acc in active_accounts]
            
            if not target_list:
                print("X API target accounts (in DB) not properly configured. Skipping X")
                return
            
            fetch_function = get_latest_posts_from_x # (★) 変更後の関数名
            get_since_value = lambda last_post: last_post.post_id if last_post else None
            provider_username_map = {username: username for username in target_list}
        
        elif API_PROVIER == "Threads":
            # (★) Threads のロジックは変更なし
            if not THREADS_ACCESS_TOKEN or not THREADS_USER_ID:
                print("Threads API client or user ID not properly configured. Skipping Threads")
                return
            target_list = [THREADS_USER_ID]
            fetch_function = get_latest_posts_from_threads
            get_since_value = lambda last_post: int(last_post.posted_at.timestamp()) if last_post else None
            provider_username_map = {THREADS_USER_ID: "my_threads_account"}
        else:
            raise ValueError(f"Invalid API_PROVIER setting in database: {API_PROVIER}")

        # --- ユーザーごとのループ ---
        for target in target_list:
            username_to_process = provider_username_map.get(target)
            print(f"---- Processing user: {target} (as user: {username_to_process}) ----")
        
            latest_post_in_db = db.query(CollectedPost).filter(CollectedPost.username == username_to_process).order_by(CollectedPost.id.desc()).first()
            since_value = get_since_value(latest_post_in_db)

            if API_PROVIER == "X":
                success, raw_posts = fetch_function(oauth_session, target, since_id=since_value) # (★) client_x -> oauth_session
            elif API_PROVIER == "Threads":
                success, raw_posts = fetch_function(target, since_value)

            if not success:
                print(f"Failed to fetch posts for user: {target}. Skipping.")
                continue
            if not raw_posts:
                print(f"No new posts found for user: {target}.")
                continue
                
            print(f"Fetched {len(raw_posts)} new posts for user: {target}.")
            
            # --- 投稿ごとのループ (古い順) ---
            for raw_post in reversed(raw_posts):
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
                    ai_summary=None,
                    link_summary=None,
                    source_url=normalized_data["source_url"],
                    posted_at=normalized_data["posted_at"],
                    like_count=normalized_data["like_count"],
                    retweet_count=normalized_data["retweet_count"]
                )

                try:
                    # (★) 1. 投稿をセッションに追加 (まだコミットしない)
                    db.add(new_collected_post)
                    db.flush() # (★) IDを取得するために flush
                    print(f"Staged post {normalized_data['post_id']} (DB ID: {new_collected_post.id})")

                    # --- AI分析の呼び出し (変更なし) ---
                    if run_ai_analysis: 
                        try:
                            print(f" -> Running AI analysis for DB ID: {new_collected_post.id}...")
                            
                            ai_result = _run_analysis_logic(
                                db=db,
                                posts_to_analyze=[new_collected_post],
                                prompt_text=prompt_template_text,
                                selected_model=ai_model_to_use,
                                selected_prompt_name=prompt_name_to_use,
                                ticker_context_map=ticker_maps
                            )
                            print(f" -> AI analysis COMPLETED (Cost: ${ai_result.get('cost_usd', 0):.6f})")
                        
                        except Exception as ai_e:
                            print(f"!!!!!!!! AI analysis FAILED for DB ID {new_collected_post.id}: {ai_e} !!!!!!!!")
                    # --- AI分析ここまで ---

                    # (★) 3. トランザクションをコミット
                    db.commit()
                    print(f"Saved post {normalized_data['post_id']} to database.")

                except IntegrityError as e:
                    db.rollback()
                    if e.orig and "duplicate key value violates unique constraint" in str(e.orig):
                        print(f"Saved Post {normalized_data['post_id']} already exists. Skipping.")
                    else:
                        print(f"An error occurred while saving post {normalized_data['post_id']}: {e}")
                except Exception as e:
                    db.rollback()
                    print(f"An unexpected error occurred while saving post {normalized_data['post_id']}: {e}")

                print(f"Waiting {SLEEP_TIME_SECONDS_BETWEEN_POSTS} seconds before next post...")
                time.sleep(SLEEP_TIME_SECONDS_BETWEEN_POSTS)

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
    """
    try:
        if provider == "X":
            if not username:
                raise ValueError("Username is required for X provider.")
            
            # ▼▼▼【変更】tweepy オブジェクトではなく、辞書(json)としてアクセス ▼▼▼
            metrics = raw_post.get("public_metrics", {})
            post_id = str(raw_post.get("id"))
            return {
                "username": username,
                "post_id": post_id,
                "text": raw_post.get("text"),
                "source_url": f"https://x.com/{username}/status/{post_id}",
                "posted_at": parse(raw_post.get("created_at")), # (★) parse() を追加
                "like_count": metrics.get("like_count", 0),
                "retweet_count": metrics.get("retweet_count", 0)
                }
            # ▲▲▲【変更ここまで】▲▲▲
            
        elif provider == "Threads":
            # (★) Threads のロジックは変更なし
            username_for_db = "my_threads_account"
            post_id = raw_post.get("id")
            if not post_id:
                raise ValueError("Post ID is missing in Threads data.")
        
            posted_at_str = raw_post.get("timestamp")
            posted_at_dt = parse(posted_at_str) if posted_at_str else None
            if not posted_at_dt:
                raise ValueError("Timestamp is missing in Threads data.")
            
            return {
                "username": username_for_db,
                "post_id": post_id,
                "text": raw_post.get("text", ""),
                "source_url": raw_post.get("permalink", ""),
                "posted_at": posted_at_dt,
                "like_count": raw_post.get("like_count", 0),
                "retweet_count": raw_post.get("reshare_count", 0)
            }
    except Exception as e:
        post_id_for_log = raw_post.get("id", "N/A")
        print(f"Error normalizing post data (Post ID: {post_id_for_log}): {e}")
        return None
    
    return None

if __name__ == "__main__":
    run_worker()