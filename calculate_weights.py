import sys
import os
from sqlalchemy import func
from models import SessionLocal, TargetAccount, UserTickerWeight

def recalculate_all_weights():
    """
    すべての監視対象アカウントの重み比率（ランキング）を再計算する。
    """
    print("--- Weight recalculation batch started ---")
    db = SessionLocal()
    try:
        # 1. すべての監視対象アカウントIDを取得
        accounts = db.query(TargetAccount.id).all()
        account_ids = [a[0] for a in accounts]
        
        total_accounts_processed = 0

        for account_id in account_ids:
            # 2. そのアカウントの「総言及回数」を計算
            # (例: { 'account_id': 1, 'total': 20 })
            result = db.query(
                func.sum(UserTickerWeight.total_mentions).label('total')
            ).filter(
                UserTickerWeight.account_id == account_id
            ).first()
            
            user_total_mentions = result.total if result and result.total else 0

            if user_total_mentions == 0:
                print(f"Skipping Account ID {account_id}: No mentions found.")
                continue

            # 3. そのアカウントの全銘柄の「比率」を更新
            # (UPDATE文を使って一括更新 - 高速)
            db.query(UserTickerWeight).filter(
                UserTickerWeight.account_id == account_id
            ).update({
                # (例: 11 / 20 = 0.55)
                'weight_ratio': UserTickerWeight.total_mentions / float(user_total_mentions)
            }, synchronize_session=False) # SQLAlchemyにキャッシュの同期をスキップさせる

            print(f"Successfully recalculated weights for Account ID {account_id} (Total Mentions: {user_total_mentions})")
            total_accounts_processed += 1

        # 4. すべての変更をコミット
        db.commit()
        print(f"--- Weight recalculation batch finished. Processed {total_accounts_processed} accounts. ---")

    except Exception as e:
        db.rollback()
        print(f"Error during weight recalculation: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # .env や models.py を読み込むためのパス設定が必要な場合がある
    # sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
    recalculate_all_weights()