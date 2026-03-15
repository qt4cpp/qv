"""Shared pytest boostrap for the whole test suite."""

import sys
import os

# Force Qt to use the offscreen backend in CI/headless test runs.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# Make the project root importable from test/.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
