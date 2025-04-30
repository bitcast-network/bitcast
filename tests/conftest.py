import os
import sys
from pathlib import Path

# Add the project root directory to the Python path
project_root = Path(__file__).resolve().parents[1]
project_parent = project_root.parent
sys.path.insert(0, str(project_root))

# Add the virtual environment site-packages to the Python path
venv_path = project_parent / "venv_bitcast"
if venv_path.exists():
    site_packages = venv_path / "lib" / "python3.8" / "site-packages"
    if site_packages.exists():
        sys.path.insert(0, str(site_packages))
    else:
        # Try to find the site-packages directory
        for lib_dir in venv_path.glob("lib/python*/site-packages"):
            sys.path.insert(0, str(lib_dir))

# This ensures that the bittensor package is in the Python path
# You might need to adjust this if bittensor is installed in a different location 