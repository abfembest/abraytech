import os
import sys

# ==============================
# PROJECT ROOT
# ==============================
BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

# ==============================
# VIRTUALENV SITE-PACKAGES
# (this replaces "source venv/bin/activate")
# ==============================
VENV_SITE_PACKAGES = (
    "/home/miuenecd/virtualenv/DigitalCampus/3.12/"
    "lib/python3.12/site-packages"
)

sys.path.insert(0, VENV_SITE_PACKAGES)

# ==============================
# DJANGO SETTINGS
# ==============================
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DigitalCampus.settings")

# ==============================
# WSGI APPLICATION
# ==============================
from DigitalCampus.wsgi import application