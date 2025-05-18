#!/bin/bash
# Script to run tests for Docker Health Exporter

# Install test dependencies if not already installed
pip install -e ".[dev]"

# Run tests with coverage
pytest --cov=docker_health_exporter tests/

# Display coverage report
coverage report -m