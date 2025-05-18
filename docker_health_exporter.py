import os
import time
import logging
import docker
import threading
import json
from flask import Flask, render_template, Response
from prometheus_client import Gauge, generate_latest, REGISTRY, CONTENT_TYPE_LATEST

# Configure logging
logger = logging.getLogger(__name__)

# Check if we're in opt-in only mode
OPT_IN_ONLY = os.environ.get("OPT_IN_ONLY", "false").lower() == "true"

# Check if we should skip default labels
NO_DEFAULT_LABELS = os.environ.get("NO_DEFAULT_LABELS", "false").lower() == "true"

# Parse label mapping configuration
LABEL_MAPPINGS = {}
LABEL_MAPPINGS_ENV = os.environ.get("LABEL_MAPPINGS", "{}")
try:
    LABEL_MAPPINGS = json.loads(LABEL_MAPPINGS_ENV)
    logger.info(f"Loaded label mappings: {LABEL_MAPPINGS}")
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse LABEL_MAPPINGS environment variable: {e}")
    logger.error(f"Using default empty mapping. LABEL_MAPPINGS was: {LABEL_MAPPINGS_ENV}")

# Define base labels for metrics
BASE_LABELS = ['container_id', 'container_name', 'image', 'project', 'service']

# Add custom labels from LABEL_MAPPINGS
CUSTOM_LABELS = list(LABEL_MAPPINGS.values())

# Determine which labels to use based on NO_DEFAULT_LABELS setting
if NO_DEFAULT_LABELS:
    logger.info("NO_DEFAULT_LABELS is set to true, using only custom labels from LABEL_MAPPINGS")
    ALL_LABELS = CUSTOM_LABELS
    # We must ensure we have at least one label or Prometheus will error
    if not CUSTOM_LABELS:
        logger.warning("NO_DEFAULT_LABELS is true but no custom labels defined in LABEL_MAPPINGS, using container_id as required label")
        ALL_LABELS = ['container_id']
else:
    ALL_LABELS = BASE_LABELS + CUSTOM_LABELS

# Prometheus metrics with dynamic labels
CONTAINER_HEALTH = Gauge(
    'docker_container_health_status',
    'Health status of Docker containers with health checks (0=unhealthy, 1=healthy, 2=starting, 3=no health check)',
    ALL_LABELS
)

# Health failure streak metric
HEALTH_FAILURE_STREAK = Gauge(
    'docker_container_health_failure_streak',
    'Number of consecutive health check failures for Docker containers',
    ALL_LABELS
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
        except Exception as e:
            logger.error(f"Failed to connect to Docker API: {e}")
            return False
            
    def should_monitor_container(self, container):
        """
        Determine if a container should be monitored based on labels.
        
        Args:
            container: Docker container object
            
        Returns:
            bool: True if the container should be monitored, False otherwise
        """
        try:
            # Get container labels
            labels = container.attrs.get('Config', {}).get('Labels', {})
            container_name = container.name if hasattr(container, 'name') else 'unknown'
            
            # Check if container is explicitly opted out
            if labels.get('prometheus.health.enabled', '').lower() == 'false':
                logger.debug(f"Container {container_name} opted out of monitoring via label")
                return False
                
            # If OPT_IN_ONLY is true, check if container is explicitly opted in
            if OPT_IN_ONLY and labels.get('prometheus.health.enabled', '').lower() != 'true':
                logger.debug(f"Container {container_name} not monitored - OPT_IN_ONLY mode and not opted in")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error determining monitoring status for container: {e}")
            return False
        
    def get_container_health(self, container):
        """
        Get health status of a container.
        
        Args:
            container: Docker container object
            
        Returns:
            dict: Dictionary with all container metadata and labels
        """
        result = {}
        
        try:
            # Extract basic container information
            container_id = container.id[:12] if hasattr(container, 'id') else 'unknown'  # Short ID
            container_name = container.name if hasattr(container, 'name') else 'unknown'
            
            if hasattr(container, 'image'):
                image_name = container.image.tags[0] if hasattr(container.image, 'tags') and container.image.tags else container.image.id[:12]
            else:
                image_name = 'unknown'
            
            # Get all container labels
            labels = container.attrs.get('Config', {}).get('Labels', {}) if hasattr(container, 'attrs') else {}
            
            # Extract compose project and service labels
            project = labels.get('com.docker.compose.project', '')
            service = labels.get('com.docker.compose.service', '')
            
            # For Docker Swarm, use different labels
            if not project:
                project = labels.get('com.docker.stack.namespace', '')
            if not service:
                service = labels.get('com.docker.swarm.service.name', '')
            
            # Check if container has health check
            health_status = 'none'
            failure_streak = 0
            if hasattr(container, 'attrs') and 'Health' in container.attrs.get('State', {}):
                health_info = container.attrs['State']['Health']
                health_status = health_info['Status']
                failure_streak = health_info.get('FailingStreak', 0)
            
            # Store all values in result dictionary, even if we're not using default labels
            # This makes it easier to access health status and failure streak values
            result = {
                'container_id': container_id,
                'container_name': container_name,
                'image': image_name,
                'project': project,
                'service': service,
                'health_status': health_status,
                'failure_streak': failure_streak
            }
            
            # Get custom label mappings from container labels
            for container_label, metric_label in LABEL_MAPPINGS.items():
                result[metric_label] = labels.get(container_label, '')
                logger.debug(f"Mapped container label {container_label} to metric label {metric_label}: {result[metric_label]}")
                
        except Exception as e:
            logger.error(f"Error getting container health info: {e}")
            # Ensure we have minimal fields for metrics
            result = {
                'container_id': getattr(container, 'id', 'unknown')[:12] if hasattr(container, 'id') else 'unknown',
                'health_status': 'none',
                'failure_streak': 0
            }
            
        return result
        
    def update_metrics(self):
        """Update Prometheus metrics with current container health statuses."""
        if not self.docker_client:
            if not self.connect_to_docker():
                logger.warning("Skipping metrics update due to Docker connection failure")
                return
                
        try:
            # Get all running containers
            if self.docker_client and hasattr(self.docker_client, 'containers'):
                containers = self.docker_client.containers.list(all=False)
                
                # Update health metrics for each container
                for container in containers:
                    try:
                        # Get container name for logging
                        container_name = container.name if hasattr(container, 'name') else str(container.id)[:12]
                        
                        # Check if this container should be monitored based on labels
                        if not self.should_monitor_container(container):
                            logger.debug(f"Skipping container {container_name} based on monitoring policy")
                            continue
                            
                        # Get container health data including any custom labels
                        container_data = self.get_container_health(container)
                        
                        # Prepare label dictionary for Prometheus metrics
                        metric_labels = {}
                        for label_name in ALL_LABELS:
                            metric_labels[label_name] = container_data.get(label_name, '')
                        
                        # Update health status metric with all labels
                        CONTAINER_HEALTH.labels(**metric_labels).set(HEALTH_STATUS.get(container_data['health_status'], 3))
                        
                        # Update failure streak metric with all labels
                        HEALTH_FAILURE_STREAK.labels(**metric_labels).set(container_data['failure_streak'])
                        
                        # Log basic info and indicate if custom labels were used
                        extra_labels = ""
                        if LABEL_MAPPINGS:
                            extra_labels = ", with custom labels"
                            
                        logger.debug(f"Container {container_data['container_name']} ({container_data['container_id']}) "
                                     f"health: {container_data['health_status']}, "
                                     f"failure streak: {container_data['failure_streak']}{extra_labels}")
                    except Exception as e:
                        container_id = getattr(container, 'id', 'unknown')[:12] if hasattr(container, 'id') else 'unknown'
                        logger.error(f"Error processing container {container_id}: {e}")
            else:
                logger.error("Docker client is not properly initialized or missing containers attribute")
                    
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
            
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
