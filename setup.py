from setuptools import setup, find_packages

setup(
    name="docker-health-exporter",
    version="1.0.0",
    description="Prometheus exporter for Docker container health checks",
    author="Docker Health Exporter Team",
    packages=find_packages(),
    install_requires=[
        "flask",
        "docker",
        "prometheus-client",
        "gunicorn",
    ],
    extras_require={
        "dev": [
            "pytest",
            "pytest-cov",
        ],
    },
    python_requires=">=3.8",
)