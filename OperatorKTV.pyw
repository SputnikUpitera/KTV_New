"""No-console Windows launcher for OperatorKTV."""

import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
os.chdir(PROJECT_ROOT)
project_root_text = str(PROJECT_ROOT)
if project_root_text not in sys.path:
    sys.path.insert(0, project_root_text)

from operator_ktv.main import main


if __name__ == "__main__":
    main()
