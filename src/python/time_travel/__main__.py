"""
允许使用 `python -m time_travel` 方式运行
"""

from .cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
