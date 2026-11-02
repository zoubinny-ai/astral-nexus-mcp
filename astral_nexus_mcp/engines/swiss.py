"""Shared Swiss Ephemeris state for all calculation engines."""
from pathlib import Path
from threading import Lock

EPHE_PATH = Path(__file__).resolve().parents[1] / 'swisseph' / 'ephe'
LOCK = Lock()
