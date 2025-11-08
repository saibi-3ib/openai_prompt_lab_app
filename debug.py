import logging, os, tweepy
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("tweepy")
logger.setLevel(logging.DEBUG)

client = tweepy.Client(
    consumer_key=os.environ.get("X_API_KEY","").strip(),
    consumer_secret=os.environ.get("X_API_KEY_SECRET","").strip(),
    access_token=os.environ.get("X_ACCESS_TOKEN","").strip(),
    access_token_secret=os.environ.get("X_ACCESS_TOKEN_SECRET","").strip(),
    wait_on_rate_limit=True
)

try:
    resp = client.get_user(username="elonmusk")
    print("client.get_user ok", resp)
except Exception as e:
    print("Exception:", type(e), e)
    if hasattr(e, "response") and e.response is not None:
        print("HTTP status:", e.response.status_code)
        print("body:", e.response.text)