# Musashi III simulator

This standalone service emulates the read-only `UL` upload exchange over a local pseudo-terminal. It replies to `D01`–`D09` requests with editable synthetic payloads from `responses.json`; it does not access or control a physical dispenser.

Run it from the repository root:

```sh
python3 simulations/iii/server.py --channels 4 --displayed-channel 1
```

The service prints its pseudo-terminal path, for example `/dev/pts/7` on Linux or `/dev/ttys004` on macOS. Set that exact path as the model III `port` in the ingestion service, choose **Synthetic simulator** as the data source, and use the same `channel_count` value. The pseudo-terminal exists only while the simulator is running. Keep the simulator process open while acquisition runs; it prints each upload and response.

For Docker Compose dev, the service uses a raw TCP serial bridge on port `9000`; configure the III port as `socket://musashi-iii:9000`. The ingestion adapter uses pySerial's socket URL handler for this one fixed development endpoint. Compose bind-mounts this response file read-only, so edits take effect after restarting the simulator service.

Change `payloads` in `responses.json` to model other valid responses. `D06` may use `{channel}`; the service fills it from `--displayed-channel`. Uploads to channels beyond `--channels` receive a synthetic `A2` rejection.
