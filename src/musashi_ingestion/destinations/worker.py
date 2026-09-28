"""Drain one target independently; failed sends retain their spool row."""


class DeliveryWorker:
    def __init__(self, spool, target_id: str, destination):
        self.spool = spool
        self.target_id = target_id
        self.destination = destination

    def drain(self, limit: int = 100) -> int:
        delivered = 0
        for record in self.spool.pending(self.target_id, limit):
            self.destination.send(record)
            self.spool.ack(self.target_id, record["record_id"])
            delivered += 1
        return delivered
