import unittest
import json
from unittest.mock import patch, MagicMock
from docker_health_exporter import create_app

class TestEndpoints(unittest.TestCase):
    """Test case for the HTTP endpoints of the Docker Health Exporter."""

    def setUp(self):
        """Set up the test environment before each test."""
        # Create a test client
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('docker_health_exporter.docker.from_env')
    def test_index_endpoint(self, mock_docker):
        """Test the index endpoint returns the documentation page."""
        # Make a request to the index endpoint
        response = self.client.get('/')

        # Check that the response is successful
        self.assertEqual(response.status_code, 200)

        # Check that it contains expected content from the template
        self.assertIn(b'Docker Healthcheck Exporter', response.data)
        self.assertIn(b'docker_container_health_status', response.data)

    @patch('docker_health_exporter.docker.from_env')
    def test_metrics_endpoint(self, mock_docker):
        """Test the metrics endpoint returns Prometheus metrics."""
        # Make a request to the metrics endpoint
        response = self.client.get('/metrics')

        # Check that the response is successful
        self.assertEqual(response.status_code, 200)

        # Check that it returns the correct content type
        self.assertIn('text/plain', response.content_type)
        self.assertIn('version=0.0.4', response.content_type)
        self.assertIn('charset=utf-8', response.content_type)

    @patch('docker_health_exporter.docker.from_env')
    def test_health_endpoint_success(self, mock_docker):
        """Test the health endpoint when Docker API is connected."""
        # Configure the mock to simulate a successful connection
        mock_docker.return_value = MagicMock()

        # Create a collector with the mocked Docker client
        with patch('docker_health_exporter.DockerHealthCollector') as mock_collector:
            # Set up the mock to indicate a successful connection
            mock_instance = mock_collector.return_value
            mock_instance.docker_client = True

            # Create a new app with the mocked collector
            test_app = create_app()
            test_client = test_app.test_client()

            # Make a request to the health endpoint
            response = test_client.get('/health')

            # Check the response
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'ok')
            self.assertEqual(data['message'], 'Connected to Docker API')

    @patch('docker_health_exporter.docker.from_env')
    def test_health_endpoint_failure(self, mock_docker):
        """Test the health endpoint when Docker API connection fails."""
        # Configure the mock to simulate a failed connection
        mock_docker.side_effect = Exception("Connection failed")

        # Create a collector with the mocked Docker client
        with patch('docker_health_exporter.DockerHealthCollector') as mock_collector:
            # Set up the mock to indicate a failed connection
            mock_instance = mock_collector.return_value
            mock_instance.docker_client = None

            # Create a new app with the mocked collector
            test_app = create_app()
            test_client = test_app.test_client()

            # Make a request to the health endpoint
            response = test_client.get('/health')

            # Check the response
            self.assertEqual(response.status_code, 500)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'error')
            self.assertEqual(data['message'], 'Not connected to Docker API')

if __name__ == '__main__':
    unittest.main()
