
from __future__ import annotations
import os, io, json, time
from typing import Optional

# Lazy imports so local runs without boto are fine
try:
    import boto3
except Exception:
    boto3 = None

class S3EventWriter:
    """Buffer events in-memory and upload JSONL chunks to S3 periodically."""
    def __init__(self, bucket: Optional[str] = None, prefix: Optional[str] = None, rotate_every: int = 1000):
        self.bucket = bucket or os.getenv("CONANBOT_S3_BUCKET", "")
        self.prefix = prefix or os.getenv("CONANBOT_S3_PREFIX", "conanbot/events")
        self.rotate_every = rotate_every
        self._buf = io.StringIO()
        self._count = 0
        self._part = 0
        self._session = None
        self._client = None

    def open(self, path):
        if boto3:
            self._session = boto3.session.Session()
            self._client = self._session.client("s3")

    def _upload(self, final: bool = False):
        if not self._client or not self.bucket:
            return
        data = self._buf.getvalue().encode("utf-8")
        if not data:
            return
        key = f"{self.prefix}/part-{self._part:05d}.jsonl"
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType="application/x-ndjson")
        self._part += 1
        self._buf = io.StringIO()
        self._count = 0

    def write(self, event):
        self._buf.write(event.model_dump_json())
        self._buf.write("\n")
        self._count += 1
        if self._count >= self.rotate_every:
            self._upload()

    def close(self):
        self._upload(final=True)
