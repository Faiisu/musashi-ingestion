# Musashi IV simulator

This standalone HTTP service answers the read-only endpoint catalog used by the IV adapter. Static responses come from `responses.json`, which is copied from the synthetic test manifest; recipe and channel item endpoints are generated for the configured capacities. The data is synthetic and is not a controller capture.

Run it from the repository root:

```sh
python3 simulations/iv/server.py --host 127.0.0.1 --port 1024 --recipes 100 --channels 400
```

Configure the ingestion service's model IV machine with the printed `host` and `port`, choose **Synthetic simulator** as the data source, and set matching `recipe_count` / `channel_count`. Ports 1024, 1025, and 1026 are accepted by the acquisition adapter. Use another allowed port if the default is occupied.

Docker Compose dev binds this service to `172.30.200.3:1024` on its private network. It does not publish the simulator port on the host. The response file is bind-mounted read-only; restart the service after editing it.

The service logs each successful GET. Unknown or excluded paths (including screen and control paths) return 404. POST returns 405. Edit `responses.json` to change static status, settings, export, clock, or log responses; recipe/channel item IDs are generated from the requested one-based URL ID and returned as zero-based `no`.
