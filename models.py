import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

engine = create_engine(DATABASE_URL.replace("postgresql://", "postgresql+psycopg://"))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- テーブル1: 監視対象アカウント ▼▼▼ ---
class TargetAccount(Base):
    """監視対象のXアカウントを保存するテーブル"""
    __tablename__ = "target_accounts"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# --- テーブル2: AIプロンプト ▼▼▼ ---
class Prompt(Base):
    """AIに渡すプロンプトのテンプレートを保存するテーブル"""
    __tablename__ = "prompts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False) # 例: 'default_summary'
    template_text = Column(Text, nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# --- テーブル3: 収集したポスト ▼▼▼ ---
class CollectedPost(Base):
    """Workerが収集した生のポスト情報を保存するテーブル"""
    __tablename__ = "collected_posts"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    post_id = Column(String, unique=True, index=True, nullable=False)
    original_text = Column(Text, nullable=False)
    source_url = Column(String, nullable=False)
    posted_at = Column(DateTime, nullable=False)
    like_count = Column(Integer, default=0)
    retweet_count = Column(Integer, default=0)
    # --- 変更点 ---
    # AI要約はオンデマンドになったので、デフォルトは空(NULL)にする
    ai_summary = Column(Text, nullable=True) 
    # リンク先の要約を保存する新しい列
    link_summary = Column(Text, nullable=True) 
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# --- テーブル4: アプリケーション設定保存用 ▼▼▼ ---
class Setting(Base):
    """アプリケーション全体の設定を保存するテーブル (キーと値のペア)"""
    """将来的に他の設定もここに追加可能"""
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True, nullable=False) # 例: 'api_provider'
    value = Column(String, nullable=False) # 例: 'X' or 'Threads'
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))