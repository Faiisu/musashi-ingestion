"""Bucket setup uses the configured organization and preserves failed deliveries."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from influxdb_client.rest import ApiException
from musashi_ingestion.destinations.factory import create_destination, DestinationSetupError
from musashi_ingestion.destinations.influx import ensure_bucket


class InfluxSetupTests(unittest.TestCase):
    def test_existing_bucket_is_reused_without_changing_retention(self):
        client = MagicMock()
        api = client.buckets_api.return_value
        api.find_buckets.return_value = SimpleNamespace(buckets=[SimpleNamespace(name="target")])
        ensure_bucket(client, "target", "org")
        api.find_buckets.assert_called_once_with(name="target", org="org")
        api.create_bucket.assert_not_called()

    def test_missing_bucket_is_created_in_configured_org(self):
        client = MagicMock()
        api = client.buckets_api.return_value
        api.find_buckets.return_value = SimpleNamespace(buckets=[])
        ensure_bucket(client, "target", "org")
        api.create_bucket.assert_called_once_with(bucket_name="target", org="org", retention_rules=[])

    def test_concurrent_creation_is_accepted_only_when_bucket_now_exists(self):
        for present in (True, False):
            with self.subTest(present=present):
                client = MagicMock()
                api = client.buckets_api.return_value
                api.find_buckets.side_effect = [
                    SimpleNamespace(buckets=[]),
                    SimpleNamespace(buckets=[SimpleNamespace(name="target")] if present else [])]
                api.create_bucket.side_effect = ApiException(status=422)
                if present:
                    ensure_bucket(client, "target", "org")
                else:
                    with self.assertRaises(ApiException):
                        ensure_bucket(client, "target", "org")

    def test_permission_denied_closes_client_and_does_not_enable_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "token"
            secret.write_text("synthetic-secret")
            config = {"kind": "influxdb", "url": "http://127.0.0.1:8086",
                      "org": "org", "bucket": "target", "secret_ref": str(secret)}
            client = MagicMock()
            client.ping.return_value = True
            client.buckets_api.return_value.find_buckets.return_value = SimpleNamespace(buckets=[])
            client.buckets_api.return_value.create_bucket.side_effect = ApiException(status=403, reason="synthetic-secret")
            with patch("influxdb_client.InfluxDBClient", return_value=client):
                with self.assertRaisesRegex(DestinationSetupError, "verify token permissions") as error:
                    create_destination(config)
            self.assertNotIn("synthetic-secret", str(error.exception))
            client.close.assert_called_once()
            client.write_api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
