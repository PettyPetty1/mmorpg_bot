# docker-compose.yml

The `docker-compose.yml` file defines containerized services for ConanBot.  
It makes local development and deployment easier by orchestrating dependencies.

## Typical services
- **FastAPI UI** — runs `apps/ui_api/main.py` with Uvicorn.
- **Kafka** — message broker for event streaming.
- **Zookeeper** — required for Kafka.
- **Optional S3-compatible storage** (e.g. MinIO) — local replacement for AWS S3.

## Usage
```bash
docker-compose up
```

This starts all services together so the system can capture events, stream them via Kafka or store them in S3, and expose the FastAPI UI.