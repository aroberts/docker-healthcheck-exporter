import os
import logging
from docker_health_exporter import create_app

# Configure logging
log_level_name = os.environ.get("LOG_LEVEL", "info").upper()
log_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# Create and run the application
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=DEBUG)
