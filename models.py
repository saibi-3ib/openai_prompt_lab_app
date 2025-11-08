import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Table, Float, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone
from flask_login import UserMixin

load_dotenv()

DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME")

# DB接続情報が .env から読み込めているかチェック
if not all([DB_USER, DB_PASSWORD, DB_NAME]):
    raise ValueError("データベース接続情報 (DB_USER, DB_PASSWORD, DB_NAME) が .env ファイルに設定されていません。")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
print(f"--- [models.py] Connecting to PostgreSQL database at: {DB_HOST}:{DB_PORT}/{DB_NAME} ---")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- ▼▼▼【以下をファイル末尾に追加】▼▼▼ ---
# --- テーブル: ユーザー情報 ---
class User(UserMixin, Base): # <-- UserMixin を継承
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), index=True, unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def get_id(self):
        return str(self.id)
# --- ▲▲▲【追加ここまで】▲▲▲ ---

# --- テーブル: 監視対象アカウント ---
class TargetAccount(Base):
    """監視対象のXアカウントを保存するテーブル"""
    __tablename__ = "target_accounts"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    provider = Column(String(20), nullable=False, default='X', index=True) # (★) 'X' or 'Threads'
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
    # (★) TickerSentimentとのリレーションシップ
    ticker_sentiments = relationship("TickerSentiment", back_populates="collected_post")

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
        secondary = analysis_posts_link,
        back_populates = "analyses" 
    ) 

    # ▼▼▼【ここから追加】コストとモデルのカラム ▼▼▼
    # 使用したAIモデル (例: gpt-4o-mini, gpt-3.5-turbo)
    ai_model = Column(String, nullable=True)
    # 消費したクレジットの概算コスト (USD)
    cost_usd = Column(Float, nullable=True)
    # 使用したトークン数 (入力)
    input_tokens = Column(Integer, nullable=True) 
    # 使用したトークン数 (出力)
    output_tokens = Column(Integer, nullable=True) 

    # AIが抽出した銘柄コード (例: "AAPL,TSLA,MSFT")
    extracted_tickers = Column(String, nullable=True, index=True) 

    # (子) このバッチ分析に含まれる個別のセンチメント結果
    sentiments = relationship(
        "TickerSentiment", 
        back_populates="analysis_result",
        order_by="TickerSentiment.collected_post_id" # (★) groupby のためにソート順を追加
    )

class StockTickerMap(Base):
    """S&P500などの銘柄と企業名、エイリアス（愛称）の変換表"""
    __tablename__ = "stock_ticker_map"
    
    ticker = Column(String(10), primary_key=True) # "AAPL"
    company_name = Column(String, nullable=False, index=True) # "Apple Inc."
    # GICS Sector (例: 'Information Technology')
    gics_sector = Column(String, nullable=True, index=True) 
    # GICS Sub-Industry (例: 'Application Software')
    gics_sub_industry = Column(String, nullable=True)


class TickerSentiment(Base):
    """投稿内の各銘柄に対するセンチメント分析結果"""
    __tablename__ = "ticker_sentiment"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # どのバッチ分析に属しているか
    analysis_result_id = Column(Integer, ForeignKey('analysis_results.id'), nullable=False, index=True)
    # どの投稿に対する分析か
    collected_post_id = Column(Integer, ForeignKey('collected_posts.id'), nullable=False, index=True)
    # どの銘柄か (ティッカーで統一)
    ticker = Column(String(10), ForeignKey('stock_ticker_map.ticker'), nullable=False, index=True)
    
    sentiment = Column(String(10), nullable=False) # "Positive", "Negative", "Neutral"
    reasoning = Column(Text, nullable=True) # AIによる判断根拠
    
    # (親) このセンチメント結果が属するバッチ分析
    analysis_result = relationship("AnalysisResult", back_populates="sentiments")
    collected_post = relationship("CollectedPost", back_populates="ticker_sentiments")

class UserTickerWeight(Base):
    """
    監視対象アカウント (TargetAccount) と銘柄 (StockTickerMap) の
    関係性（重み）を「総言及回数」と「正規化比率」として蓄積するテーブル。
    """
    __tablename__ = "user_ticker_weights"
    
    id = Column(Integer, primary_key=True)
    
    # 外部キー: どの監視対象アカウントか
    account_id = Column(Integer, ForeignKey('target_accounts.id'), nullable=False, index=True)
    
    # 外部キー: どの銘柄か
    ticker = Column(String(10), ForeignKey('stock_ticker_map.ticker'), nullable=False, index=True)
    
    # 蓄積値 (言及回数) - フェーズ2で更新
    total_mentions = Column(Integer, nullable=False, default=0)
    
    # 重み付け (正規化比率: 0.0 ～ 1.0) - フェーズ3で更新
    weight_ratio = Column(Float, nullable=False, default=0.0, index=True)
    
    last_analyzed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('account_id', 'ticker', name='_account_ticker_uc'),)