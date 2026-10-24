#!/opt/hes-trade-agent/.venv/bin/python
from pathlib import Path
import sys
ROOT=Path('/opt/hes-trade-agent')
sys.path.insert(0,str(ROOT))
from forward.global_market_data_gateio_v1 import run
run()
