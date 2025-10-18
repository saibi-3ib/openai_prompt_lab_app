import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL')

# Renderから提供されるDATABASE_URLが存在しない場合はエラーを出す
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Did you set it in Render?")

# 'psycopg'ドライバを明示的に使用するようにURLを書き換える
engine = create_engine(DATABASE_URL.replace("postgresql://", "postgresql+psycopg://"))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class CollectedPost(Base):
    __tablename__ = "collected_posts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    post_id = Column(String, unique=True, index=True, nullable=False)
    posted_at = Column(DateTime, nullable=False) 
    original_text = Column(Text, nullable=False)
    ai_summary = Column(Text, nullable=True)
    source_url = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    like_count = Column(Integer, default=0)    
    retweet_count = Column(Integer, default=0) 

def init_db():
    Base.metadata.create_all(bind=engine)

# スクリプトとして直接実行された場合にDBを初期化する
if __name__ == "__main__":
    print("Initializing the database...")
    init_db()
    print("Database initialized.")

    #/Users/30ryo/development/xbot_for_investors/models.py