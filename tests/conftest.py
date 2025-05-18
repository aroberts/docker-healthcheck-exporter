"""
Configuration for pytest.
"""
import os
import sys

# Add the project root directory to the Python path to ensure imports work properly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))