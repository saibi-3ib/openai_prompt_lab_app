from models import SessionLocal, CollectedPost
from datetime import datetime, timezone

def run_worker():
    print(f"Cron Job started at {datetime.now(timezone.utc).isoformat()}")
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        post_id = f"dummy_post_{int(now.timestamp())}"
        
        existing_post = db.query(CollectedPost).filter(CollectedPost.post_id == post_id).first()
        if not existing_post:
            new_post = CollectedPost(
                post_id=post_id,
                original_text="This is a sample text collected by the cron job.",
                processed_data=f"Processed at {now.isoformat()}",
                source_url=f"https://example.com/post/{post_id}"
            )
            db.add(new_post)
            db.commit()
            print(f"New data added: {post_id}")
        else:
            print(f"Data already exists: {post_id}")

    except Exception as e:
        print(f"An error occurred: {e}")
        db.rollback()
    finally:
        db.close()
        print("Cron Job finished.")

if __name__ == "__main__":
    run_worker()