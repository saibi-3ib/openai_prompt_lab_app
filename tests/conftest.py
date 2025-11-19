import sys
from pathlib import Path

# project root: 親ディレクトリ（tests/ の一つ上）
ROOT = Path(__file__).resolve().parents[1]
# 先頭に追加して、ローカルの app パッケージが優先されるようにする
sys.path.insert(0, str(ROOT))
