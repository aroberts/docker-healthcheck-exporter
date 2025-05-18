import unittest
from unittest.mock import patch, MagicMock
from docker_health_exporter import DockerHealthCollector, HEALTH_STATUS

class TestDockerHealthCollector(unittest.TestCase):
    """Test case for the DockerHealthCollector class."""

    def setUp(self):
        """Set up the test environment before each test."""
        # Create a collector with mocked Docker client
        self.patcher = patch('docker_health_exporter.docker.from_env')
        self.mock_docker = self.patcher.start()
        self.mock_client = MagicMock()
        self.mock_docker.return_value = self.mock_client

        # Create the collector
        self.collector = DockerHealthCollector()

    def tearDown(self):
        """Tear down the test environment after each test."""
        self.patcher.stop()

    def test_connect_to_docker_success(self):
        """Test connecting to Docker API successfully."""
        # Configure the mock to return successfully
        self.mock_docker.return_value = self.mock_client

        # Call the method
        result = self.collector.connect_to_docker()

        # Check the result
        self.assertTrue(result)
        self.assertEqual(self.collector.docker_client, self.mock_client)

    def test_connect_to_docker_failure(self):
        """Test connecting to Docker API with failure."""
        # Configure the mock to raise an exception
        self.mock_docker.side_effect = Exception("Connection failed")

        # Call the method
        result = self.collector.connect_to_docker()

        # Check the result
        self.assertFalse(result)
        self.assertIsNone(self.collector.docker_client)

    def test_should_monitor_container_opt_in_only_false(self):
        """Test should_monitor_container with OPT_IN_ONLY=False."""
        # Create a mock container
        mock_container = MagicMock()

        # Configure the container's attributes
        mock_container.attrs = {
            'Config': {
                'Labels': {}
            }
        }

        # Test with a container with no labels (should be monitored)
        with patch('docker_health_exporter.OPT_IN_ONLY', False):
            result = self.collector.should_monitor_container(mock_container)
            self.assertTrue(result)

        # Test with a container explicitly opted out
        mock_container.attrs['Config']['Labels'] = {
            'prometheus.health.enabled': 'false'
        }
        with patch('docker_health_exporter.OPT_IN_ONLY', False):
            result = self.collector.should_monitor_container(mock_container)
            self.assertFalse(result)

    def test_should_monitor_container_opt_in_only_true(self):
        """Test should_monitor_container with OPT_IN_ONLY=True."""
        # Create a mock container
        mock_container = MagicMock()

        # Configure the container's attributes
        mock_container.attrs = {
            'Config': {
                'Labels': {}
            }
        }

        # Test with a container with no labels (should not be monitored)
        with patch('docker_health_exporter.OPT_IN_ONLY', True):
            result = self.collector.should_monitor_container(mock_container)
            self.assertFalse(result)

        # Test with a container explicitly opted in
        mock_container.attrs['Config']['Labels'] = {
            'prometheus.health.enabled': 'true'
        }
        with patch('docker_health_exporter.OPT_IN_ONLY', True):
            result = self.collector.should_monitor_container(mock_container)
            self.assertTrue(result)

    def test_get_container_health(self):
        """Test get_container_health retrieves and processes container health data."""
        # Create a mock container
        mock_container = MagicMock()
        mock_container.id = "abc123def456"
        mock_container.name = "test-container"
        mock_container.image.tags = ["nginx:latest"]

        # Configure container attributes with health check
        mock_container.attrs = {
            'Config': {
                'Labels': {
                    'com.docker.compose.project': 'testproject',
                    'com.docker.compose.service': 'web',
                    'com.example.team': 'devops'
                }
            },
            'State': {
                'Health': {
                    'Status': 'healthy',
                    'FailingStreak': 0
                }
            }
        }

        # Test with default settings
        result = self.collector.get_container_health(mock_container)

        # Check result contains the expected values
        self.assertEqual(result['container_id'], 'abc123def456')
        self.assertEqual(result['container_name'], 'test-container')
        self.assertEqual(result['image'], 'nginx:latest')
        self.assertEqual(result['stack'], 'testproject')
        self.assertEqual(result['service'], 'web')
        self.assertEqual(result['health_status'], 'healthy')
        self.assertEqual(result['failure_streak'], 0)

        # Test with custom label mappings
        with patch('docker_health_exporter.LABEL_MAPPINGS', {'com.example.team': 'team'}):
            result = self.collector.get_container_health(mock_container)
            self.assertEqual(result['team'], 'devops')

    def test_get_container_health_no_health_check(self):
        """Test get_container_health with a container that has no health check."""
        # Create a mock container
        mock_container = MagicMock()
        mock_container.id = "abc123def456"
        mock_container.name = "test-container"
        mock_container.image.tags = ["nginx:latest"]

        # Configure container attributes without health check
        mock_container.attrs = {
            'Config': {
                'Labels': {
                    'com.docker.compose.project': 'testproject',
                    'com.docker.compose.service': 'web'
                }
            },
            'State': {
                # No Health key
            }
        }

        # Get container health
        result = self.collector.get_container_health(mock_container)

        # Check result has the correct default values
        self.assertEqual(result['health_status'], 'none')
        self.assertEqual(result['failure_streak'], 0)

    def test_update_metrics(self):
        """Test update_metrics processes containers and updates metrics."""
        # Mock the containers list
        mock_container1 = MagicMock()
        mock_container1.id = "container1"
        mock_container1.name = "test-container-1"

        mock_container2 = MagicMock()
        mock_container2.id = "container2"
        mock_container2.name = "test-container-2"

        self.mock_client.containers.list.return_value = [mock_container1, mock_container2]

        # Mock the should_monitor_container method
        with patch.object(self.collector, 'should_monitor_container') as mock_should_monitor:
            # First container should be monitored, second one not
            mock_should_monitor.side_effect = [True, False]

            # Mock the get_container_health method
            with patch.object(self.collector, 'get_container_health') as mock_get_health:
                mock_get_health.return_value = {
                    'container_id': 'container1',
                    'container_name': 'test-container-1',
                    'image': 'nginx:latest',
                    'stack': 'testproject',
                    'service': 'web',
                    'health_status': 'healthy',
                    'failure_streak': 0
                }

                # Mock the metrics gauges
                with patch('docker_health_exporter.CONTAINER_HEALTH') as mock_health_gauge, \
                     patch('docker_health_exporter.HEALTH_FAILURE_STREAK') as mock_streak_gauge:

                    # Configure the mock gauges
                    mock_labels = MagicMock()
                    mock_health_gauge.labels.return_value = mock_labels
                    mock_streak_gauge.labels.return_value = mock_labels

                    # Call update_metrics
                    self.collector.update_metrics()

                    # Verify methods called correctly
                    self.mock_client.containers.list.assert_called_once_with(all=False)
                    self.assertEqual(mock_should_monitor.call_count, 2)
                    mock_get_health.assert_called_once_with(mock_container1)

                    # Check that metrics were updated for the monitored container
                    mock_health_gauge.labels.assert_called_once()
                    mock_streak_gauge.labels.assert_called_once()
                    mock_labels.set.assert_called_with(HEALTH_STATUS.get('unhealthy', 3))

if __name__ == '__main__':
    unittest.main()
