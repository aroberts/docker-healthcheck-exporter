import os
import time
import logging
import docker
import threading
from flask import Flask, render_template, Response
from prometheus_client import Gauge, generate_latest, REGISTRY, CONTENT_TYPE_LATEST

# Configure logging
logger = logging.getLogger(__name__)

# Prometheus metrics
CONTAINER_HEALTH = Gauge(
    'docker_container_health_status',
    'Health status of Docker containers with health checks (0=unhealthy, 1=healthy, 2=starting, 3=no health check)',
    ['container_id', 'container_name', 'image']
)

# Health status mapping
HEALTH_STATUS = {
    'unhealthy': 0,
    'healthy': 1,
    'starting': 2,
    'none': 3
}

class DockerHealthCollector:
    """Collector for Docker container health metrics."""
    
    def __init__(self, poll_interval=15):
        """
        Initialize the Docker health collector.
        
        Args:
            poll_interval (int): Interval in seconds to poll Docker API
        """
        self.poll_interval = poll_interval
        self.docker_client = None
        self.running = False
        
    def connect_to_docker(self):
        """Establish connection to Docker API."""
        try:
            self.docker_client = docker.from_env()
            logger.info("Successfully connected to Docker API")
            return True
        except docker.errors.DockerException as e:
            logger.error(f"Failed to connect to Docker API: {e}")
            return False
            
    def get_container_health(self, container):
        """
        Get health status of a container.
        
        Args:
            container: Docker container object
            
        Returns:
            tuple: (container_id, container_name, image_name, health_status)
        """
        container_id = container.id[:12]  # Short ID
        container_name = container.name
        image_name = container.image.tags[0] if container.image.tags else container.image.id[:12]
        
        # Check if container has health check
        health_status = 'none'
        if hasattr(container, 'attrs') and 'Health' in container.attrs.get('State', {}):
            health_status = container.attrs['State']['Health']['Status']
        
        return container_id, container_name, image_name, health_status
        
    def update_metrics(self):
        """Update Prometheus metrics with current container health statuses."""
        if not self.docker_client:
            if not self.connect_to_docker():
                logger.warning("Skipping metrics update due to Docker connection failure")
                return
                
        try:
            # Get all running containers
            containers = self.docker_client.containers.list(all=False)
            
            # Update health metrics for each container
            for container in containers:
                try:
                    container_id, container_name, image_name, health_status = self.get_container_health(container)
                    CONTAINER_HEALTH.labels(
                        container_id=container_id,
                        container_name=container_name,
                        image=image_name
                    ).set(HEALTH_STATUS.get(health_status, 3))
                    
                    logger.debug(f"Container {container_name} ({container_id}) health: {health_status}")
                except Exception as e:
                    logger.error(f"Error processing container {container.id}: {e}")
                    
        except docker.errors.APIError as e:
            logger.error(f"Docker API error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error updating metrics: {e}")
            
    def start_polling(self):
        """Start polling Docker API in a separate thread."""
        def poll_loop():
            logger.info(f"Starting polling thread with interval of {self.poll_interval} seconds")
            while self.running:
                try:
                    self.update_metrics()
                except Exception as e:
                    logger.error(f"Error in polling thread: {e}")
                time.sleep(self.poll_interval)
                
        self.running = True
        polling_thread = threading.Thread(target=poll_loop, daemon=True)
        polling_thread.start()
        
    def stop_polling(self):
        """Stop the polling thread."""
        self.running = False

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Create and start the Docker health collector
    collector = DockerHealthCollector(
        poll_interval=int(os.environ.get("POLL_INTERVAL", "15"))
    )
    collector.start_polling()
    
    @app.route('/')
    def index():
        """Render the main monitoring page."""
        return render_template('index.html')
    
    @app.route('/metrics')
    def metrics():
        """Expose Prometheus metrics endpoint."""
        return Response(generate_latest(REGISTRY), mimetype=CONTENT_TYPE_LATEST)
    
    @app.route('/health')
    def health():
        """Health check endpoint."""
        if collector.docker_client:
            return {"status": "ok", "message": "Connected to Docker API"}
        else:
            return {"status": "error", "message": "Not connected to Docker API"}, 500
    
    return app
