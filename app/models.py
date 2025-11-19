"""
アプリケーションの SQLAlchemy モデル定義（Flask‑SQLAlchemy を前提）。

注意:
- 既存の app/models.py を置換する前にバックアップを取ってください:
    cp app/models.py app/models.py.bak
- このファイルは import 時に致命的な例外を投げないように設計してあります（CI や alembic の import 時の失敗を防止）。
- パスやアプリ構成に合わせて必要に応じて調整してください。
"""

from datetime import datetime

from flask import current_app
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


# ---- ユーティリティ / 共通設定 ----
def _now():
    return datetime.utcnow()


# ---- モデル定義 ----
class Prompt(db.Model):
    __tablename__ = "prompts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False, unique=True)
    template_text = db.Column(db.Text, nullable=False)
    is_default = db.Column(db.Boolean, nullable=True, default=False)
    created_at = db.Column(db.DateTime, default=_now)

    def __repr__(self) -> str:
        return f"<Prompt id={self.id} name={self.name}>"


class Setting(db.Model):
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String, nullable=False, unique=True)
    value = db.Column(db.String, nullable=False)
    updated_at = db.Column(db.DateTime, default=_now)

    def __repr__(self) -> str:
        return f"<Setting {self.key}={self.value}>"


class StockTickerMap(db.Model):
    __tablename__ = "stock_ticker_map"

    ticker = db.Column(db.String(10), primary_key=True)
    company_name = db.Column(db.String, nullable=False)
    gics_sector = db.Column(db.String, nullable=True)
    gics_sub_industry = db.Column(db.String, nullable=True)

    def __repr__(self) -> str:
        return f"<StockTickerMap {self.ticker} {self.company_name}>"


class TargetAccount(db.Model):
    __tablename__ = "target_accounts"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, nullable=False, unique=True, index=True)
    provider = db.Column(db.String(20), nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    added_at = db.Column(db.DateTime, default=_now)

    # relationship: one-to-many -> CollectedPost
    collected_posts = db.relationship(
        "CollectedPost",
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<TargetAccount id={self.id} provider={self.provider} username={self.username}>"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=_now)

    # 任意のフラグ（既存コードが is_admin を参照する場合に対応）
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    # UserMixin が is_authenticated / is_active / is_anonymous / get_id を提供します。
    # 追加でヘルパーが欲しければここに実装できます。

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class AnalysisResult(db.Model):
    __tablename__ = "analysis_results"

    id = db.Column(db.Integer, primary_key=True)
    prompt_id = db.Column(
        db.Integer, db.ForeignKey("prompts.id"), nullable=False, index=True
    )
    raw_json_response = db.Column(db.Text, nullable=True)
    extracted_summary = db.Column(db.Text, nullable=True)
    analyzed_at = db.Column(db.DateTime, nullable=True)
    ai_model = db.Column(db.String, nullable=True)
    cost_usd = db.Column(db.Float, nullable=True)
    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    extracted_tickers = db.Column(db.String, nullable=True)

    prompt = db.relationship(
        "Prompt", backref=db.backref("analysis_results", lazy="select")
    )

    # many-to-many -> CollectedPost via association table analysis_posts_link
    analysis_posts_link_rows = db.relationship(
        "AnalysisPostsLink",
        back_populates="analysis_result",
        lazy="select",
        overlaps="analysis_results,collected_posts,analysis_posts_link_rows",
    )
    collected_posts = db.relationship(
        "CollectedPost",
        secondary="analysis_posts_link",
        back_populates="analysis_results",
        lazy="select",
        overlaps="analysis_posts_link_rows",
    )

    ticker_sentiments = db.relationship(
        "TickerSentiment", back_populates="analysis_result", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<AnalysisResult id={self.id} prompt_id={self.prompt_id}>"


class CollectedPost(db.Model):
    __tablename__ = "collected_posts"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(
        db.String, db.ForeignKey("target_accounts.username"), nullable=False, index=True
    )
    post_id = db.Column(db.String, nullable=False, unique=True, index=True)
    original_text = db.Column(db.Text, nullable=False)
    source_url = db.Column(db.String, nullable=False)
    posted_at = db.Column(db.DateTime, nullable=False)
    like_count = db.Column(db.Integer, nullable=True)
    retweet_count = db.Column(db.Integer, nullable=True)
    ai_summary = db.Column(db.Text, nullable=True)
    link_summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_now)

    account = db.relationship(
        "TargetAccount", back_populates="collected_posts", lazy="joined"
    )
    analysis_posts_link_rows = db.relationship(
        "AnalysisPostsLink",
        back_populates="collected_post",
        lazy="select",
        overlaps="analysis_results,collected_posts,analysis_posts_link_rows",
    )
    analysis_results = db.relationship(
        "AnalysisResult",
        secondary="analysis_posts_link",
        back_populates="collected_posts",
        lazy="select",
        overlaps="analysis_posts_link_rows",
    )

    ticker_sentiments = db.relationship(
        "TickerSentiment", back_populates="collected_post", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<CollectedPost id={self.id} post_id={self.post_id} username={self.username}>"


class UserTickerWeight(db.Model):
    __tablename__ = "user_ticker_weights"
    __table_args__ = (
        db.UniqueConstraint("account_id", "ticker", name="_account_ticker_uc"),
    )

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(
        db.Integer, db.ForeignKey("target_accounts.id"), nullable=False, index=True
    )
    ticker = db.Column(
        db.String(10),
        db.ForeignKey("stock_ticker_map.ticker"),
        nullable=False,
        index=True,
    )
    total_mentions = db.Column(db.Integer, nullable=False, default=0)
    weight_ratio = db.Column(db.Float, nullable=False, default=0.0)
    last_analyzed_at = db.Column(db.DateTime, nullable=True)

    account = db.relationship("TargetAccount", lazy="joined")
    ticker_map = db.relationship("StockTickerMap", lazy="joined")

    def __repr__(self) -> str:
        return f"<UserTickerWeight account_id={self.account_id} ticker={self.ticker} weight={self.weight_ratio}>"


class AnalysisPostsLink(db.Model):
    __tablename__ = "analysis_posts_link"

    analysis_result_id = db.Column(
        db.Integer, db.ForeignKey("analysis_results.id"), primary_key=True
    )
    collected_post_id = db.Column(
        db.Integer, db.ForeignKey("collected_posts.id"), primary_key=True
    )

    analysis_result = db.relationship(
        "AnalysisResult",
        back_populates="analysis_posts_link_rows",
        overlaps="analysis_results,collected_posts,analysis_posts_link_rows",
    )
    collected_post = db.relationship(
        "CollectedPost",
        back_populates="analysis_posts_link_rows",
        overlaps="analysis_results,collected_posts,analysis_posts_link_rows",
    )

    def __repr__(self) -> str:
        return f"<AnalysisPostsLink ar={self.analysis_result_id} cp={self.collected_post_id}>"


class TickerSentiment(db.Model):
    __tablename__ = "ticker_sentiment"

    id = db.Column(db.Integer, primary_key=True)
    analysis_result_id = db.Column(
        db.Integer, db.ForeignKey("analysis_results.id"), nullable=False, index=True
    )
    collected_post_id = db.Column(
        db.Integer, db.ForeignKey("collected_posts.id"), nullable=False, index=True
    )
    ticker = db.Column(
        db.String(10),
        db.ForeignKey("stock_ticker_map.ticker"),
        nullable=False,
        index=True,
    )
    sentiment = db.Column(db.String(10), nullable=False)
    reasoning = db.Column(db.Text, nullable=True)

    analysis_result = db.relationship(
        "AnalysisResult", back_populates="ticker_sentiments", lazy="joined"
    )
    collected_post = db.relationship(
        "CollectedPost", back_populates="ticker_sentiments", lazy="joined"
    )
    ticker_map = db.relationship("StockTickerMap", lazy="joined")

    def __repr__(self) -> str:
        return f"<TickerSentiment {self.ticker} sentiment={self.sentiment}>"


# ---- モデルモジュールの初期化時に実行する安全チェック (インポート時に致命的エラーを出さない) ----
# 以前はここで .env の DB_* を必須として例外を投げていた可能性があります。
# ここでは import 時には致命的な例外は投げず、必要なら警告を出してフォールバックします。
try:
    # Flask アプリコンテキストが存在する場合は、設定値の検査を行うことができます。
    cfg = current_app.config if current_app else None  # type: ignore
    # もし本番環境の必須設定チェックをしたい場合は、create_app 内で実施してください。
except Exception:
    # current_app が未作成の場合（テスト/CI）はここに到達します。無視して続行。
    pass
