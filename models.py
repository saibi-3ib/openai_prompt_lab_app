import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Table
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone

load_dotenv()

# プロジェクトのルートディレクトリへの絶対パスを取得
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
#.envファイルからデータベースURLを取得、もしくはデフォルトの'app.db'を使用
DB_NAME = os.environ.get("DB_FILENAME", "app.db")
# 絶対パスのデータベースURLを構築
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, DB_NAME)}"
print(f"--- [models.py] Connecting to database at: {os.path.join(BASE_DIR, DB_NAME)} ---") # デバッグ用出力

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- テーブル: 監視対象アカウント ---
class TargetAccount(Base):
    """監視対象のXアカウントを保存するテーブル"""
    __tablename__ = "target_accounts"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# --- テーブル: AIプロンプト ---
class Prompt(Base):
    """AIに渡すプロンプトのテンプレートを保存するテーブル"""
    __tablename__ = "prompts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False) # 例: 'default_summary'
    template_text = Column(Text, nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# --- テーブル: （連結テーブル）分析と投稿の多対多関連 ---
# Baseを継承しないSQLAlchemy Coreスタイルのテーブル定義
analysis_posts_link = Table('analysis_posts_link', Base.metadata,
    Column('analysis_result_id', Integer, ForeignKey('analysis_results.id'), primary_key=True),
    Column('collected_post_id', Integer, ForeignKey('collected_posts.id'), primary_key=True)
)

# --- テーブル: 収集したポスト ---
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

    analyses = relationship(
        "AnalysisResult", 
        secondary = analysis_posts_link,  # analysis_posts_linkテーブルを経由
        back_populates = "posts" # AnalysisResult側の"posts"と相互参照
    )
# --- テーブル: アプリケーション設定保存用 ---
class Setting(Base):
    """アプリケーション全体の設定を保存するテーブル (キーと値のペア)"""
    """将来的に他の設定もここに追加可能"""
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True, nullable=False) # 例: 'api_provider'
    value = Column(String, nullable=False) # 例: 'X' or 'Threads'
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

# --- テーブル: AI分析結果保存用 ---
class AnalysisResult(Base):
    """どの投稿をどのプロンプトで分析したかを保存するテーブル"""
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)

    # 外部キー: 使用したプロンプト
    prompt_id = Column(Integer, ForeignKey('prompts.id'), nullable=False, index=True)

    # AIからの生のJSONレスポンス全体
    raw_json_response = Column(Text, nullable=True)

    # JSONから抽出した主要な結果("summary"など)
    extracted_summary = Column(Text, nullable=True)

    # (任意) センチメントや銘柄など、将来的に抽出するデータ用のカラム
    # extracted_sentiment = Column(String, nullable=True)
    # extracted_tickers = Column(String, nullable=True)

    analyzed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # リレーションシップ定義("Prompt")
    prompt = relationship("Prompt")

    # この分析のために使用した投稿群リスト (多対多)
    posts = relationship(
        "CollectedPost", 
        secondary = analysis_posts_link,  # analysis_posts_linkテーブルを経由
        back_populates = "analyses" # CollectedPost側の"analyses"と相互参照 
    ) 