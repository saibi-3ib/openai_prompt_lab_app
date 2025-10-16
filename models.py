import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

load_dotenv()

"""
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    # ローカル開発用に、DATABASE_URLが設定されていない場合の仮のURLを設定
    DATABASE_URL = "postgresql://user:password@localhost/mydatabase"
"""
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    # ローカル開発用に、SQLiteを使用する
    DATABASE_URL = "sqlite:///./local_database.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class CollectedPost(Base):
    __tablename__ = "collected_posts"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(String, unique=True, index=True, nullable=False)
    original_text = Column(Text, nullable=False)
    processed_data = Column(Text, nullable=True)
    source_url = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

def init_db():
    Base.metadata.create_all(bind=engine)

# スクリプトとして直接実行された場合にDBを初期化する
if __name__ == "__main__":
    print("Initializing the database...")
    init_db()
    print("Database initialized.")