# Small script to generate many test posts and related ticker sentiments for local testing.
# Usage: python scripts/generate_test_data.py --count 5000
import random
import argparse
from datetime import datetime, timezone, timedelta
from models import SessionLocal, CollectedPost, TickerSentiment, TargetAccount, StockTickerMap, Prompt, AnalysisResult
import string

SAMPLE_TICKERS = ['AAPL','TSLA','MSFT','AMZN','GOOG','FB','NFLX','NVDA','INTC','AMD','BABA','FOX']

def random_text():
    words = ['market','price','buy','sell','earnings','growth','quarter','guidance','downgrade','upgrade','rumor','ipo']
    return ' '.join(random.choices(words, k=random.randint(6,20)))

def ensure_seed_data(db):
    # ensure tickers exist
    for t in SAMPLE_TICKERS:
        existing = db.query(StockTickerMap).filter(StockTickerMap.ticker==t).first()
        if not existing:
            db.add(StockTickerMap(ticker=t, company_name=f"{t} Corp", gics_sector='Technology', gics_sub_industry='Software'))
    db.commit()

def generate(count):
    db = SessionLocal()
    try:
        ensure_seed_data(db)
        # ensure a few target accounts exist
        usernames = [f"user_{i}" for i in range(1,21)]
        for u in usernames:
            if not db.query(TargetAccount).filter(TargetAccount.username==u).first():
                db.add(TargetAccount(username=u, provider='X'))
        db.commit()

        # --- 新規: テスト用の Prompt がなければ作成し、ダミーの AnalysisResult を作成して ID を使う ---
        prompt = db.query(Prompt).first()
        if not prompt:
            # Prompt テーブルの必須カラムに合わせて適宜設定
            prompt = Prompt(name='__test_prompt__', template_text='Test prompt template')
            db.add(prompt)
            db.commit()

        # Create a single dummy AnalysisResult to attach sentiments to (avoid NOT NULL FK issues)
        dummy_result = AnalysisResult(
            prompt_id=prompt.id,
            raw_json_response='{"test": true}',
            extracted_summary='dummy'
        )
        db.add(dummy_result)
        db.commit()
        dummy_result_id = dummy_result.id

        # start inserting
        now = datetime.now(timezone.utc)
        added = 0
        for i in range(count):
            u = random.choice(usernames)
            posted_at = now - timedelta(seconds=random.randint(0, 60*60*24*30))
            post = CollectedPost(
                username=u,
                post_id='test_' + ''.join(random.choices(string.ascii_lowercase+string.digits, k=10)),
                original_text=random_text(),
                source_url='https://example.com',
                posted_at=posted_at,
                like_count=random.randint(0,500),
                retweet_count=random.randint(0,300),
                created_at=datetime.now(timezone.utc)
            )
            db.add(post)
            db.flush()  # get id

            # add 0-3 ticker sentiments for this post, linking to dummy_result_id
            for _ in range(random.randint(0,3)):
                t = random.choice(SAMPLE_TICKERS)
                ts = TickerSentiment(
                    analysis_result_id = dummy_result_id,
                    collected_post_id = post.id,
                    ticker = t,
                    sentiment = random.choice(['Positive','Negative','Neutral']),
                    reasoning = 'auto generated'
                )
                db.add(ts)
            if i % 100 == 0:
                db.commit()
            added += 1
        db.commit()
        print(f"Inserted {added} posts with sentiments.")
    finally:
        db.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=1000, help='number of posts to generate')
    args = parser.parse_args()
    generate(args.count)