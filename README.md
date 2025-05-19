# Docker Healthcheck Exporter

A Python-based Prometheus exporter that monitors Docker container health checks
and exposes their status as metrics.

## Overview

This exporter monitors Docker containers with health checks and exposes their
status as Prometheus metrics. It allows you to track the health status of your
containers and receive alerts when containers become unhealthy.

## Metrics

The exporter provides the following metrics:

| Metric | Description | Labels |
|--------|-------------|--------|
| `docker_container_health_status` | Health status of Docker containers with health checks | `container_id`, `container_name`, `image`, `stack`, `service` (plus any custom labels) |
| `docker_container_health_failure_streak` | Number of consecutive health check failures for Docker containers | `container_id`, `container_name`, `image`, `stack`, `service` (plus any custom labels) |

### Health Status Values

The health status is represented by the following values:

- **0** - Unhealthy
- **1** - Healthy
- **2** - Starting
- **3** - No Health Check

## Configuration

The exporter can be configured using the following environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `POLL_INTERVAL` | Interval in seconds to poll Docker API | 15 |
| `OPT_IN_ONLY` | If set to "true", only monitor containers with `prometheus.health.enabled=true` label | false |
| `LABEL_MAPPINGS` | JSON object mapping container labels to metric labels | `{}` |
| `NO_DEFAULT_LABELS` | If set to "true", only labels defined in LABEL_MAPPINGS will be included in metrics | false |
| `LOG_LEVEL` | Sets the application's logging verbosity (`debug`, `info`, `warning`, `error`, `critical`) | `info` |
| `DEBUG` | If set to "true", runs Flask in Debug mode | false |

## Container Labels

The exporter respects the following special labels:

| Label | Description |
|-------|-------------|
| `prometheus.health.enabled=false` | Explicitly opt out a container from health monitoring |
| `prometheus.health.enabled=true` | Explicitly opt in a container for health monitoring (required when `OPT_IN_ONLY=true`) |

## Dynamic Label Mapping

The exporter can copy container labels to metric labels using the `LABEL_MAPPINGS` configuration.

### Example

If you set `LABEL_MAPPINGS='{"com.example.team":"team", "com.example.app":"application"}'`, then:

- Container label `com.example.team` will be mapped to metric label `team`
- Container label `com.example.app` will be mapped to metric label `application`

Your metrics will then include these additional labels, which allows filtering and grouping in Prometheus:

```
docker_container_health_status{container_id="abc123", container_name="web-server", image="nginx:latest", stack="mystack", service="web", team="frontend", application="website"} 1
```

### Custom Labels Only

If you want to use only your custom labels without the default ones, set `NO_DEFAULT_LABELS=true`:

```
docker_container_health_status{team="frontend", application="website"} 1
```

This feature is useful for including metadata from your containers in your monitoring system, such as:

- Team ownership information
- Environment information (prod, staging, test)
- Application or service identifiers
- Custom business-relevant metadata

## Usage with Docker

### Pre-built Image

You can pull the pre-built Docker image from GitHub Container Registry:

```bash
docker pull ghcr.io/aroberts/docker-health-exporter:latest
docker run -d --name health-exporter \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -p 5000:5000 \
  ghcr.io/aroberts/docker-health-exporter:latest
```

### Building Your Own Image

Alternatively, you can build the image yourself:

```bash
docker build -t docker-health-exporter .
docker run -d --name health-exporter \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -p 5000:5000 \
  docker-health-exporter
```

Be sure to mount the Docker socket so the exporter can access the Docker API.
If you'd rather not mount the socket, the connection is made using the python
Docker API, and [can be configured from the
environment](https://docker-py.readthedocs.io/en/stable/client.html#envvar-DOCKER_HOST).

### Environment Variables

You can configure the exporter by passing environment variables to the Docker container:

```bash
docker run -d --name health-exporter \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -p 5000:5000 \
  -e POLL_INTERVAL=30 \
  -e LOG_LEVEL=debug \
  -e LABEL_MAPPINGS='{"com.example.team":"team"}' \
  ghcr.io/aroberts/docker-health-exporter:latest
```

## Endpoints

- **/** - Main page with documentation
- **/metrics** - Prometheus metrics endpoint
- **/health** - Health check endpoint to monitor the exporter itself

## Setting Up Prometheus

Add the following to your `prometheus.yml` configuration:

```yaml
scrape_configs:
  - job_name: 'docker-healthchecks'
    scrape_interval: 30s
    static_configs:
      - targets: ['localhost:5000']
```

Replace `localhost:5000` with the appropriate hostname and port where the exporter is running.
