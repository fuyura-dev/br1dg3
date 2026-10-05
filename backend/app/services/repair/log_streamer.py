import asyncio

class LogStreamer:
    def __init__(self):
        self.logs = []
        self.subscribers = []

    def log(self, message: str):
        print(message)
        self.logs.append(message)
        # Keep only the last 1000 logs to prevent memory leak
        if len(self.logs) > 1000:
            self.logs = self.logs[-1000:]

    async def subscribe(self):
        import json
        # We start yielding from the current end of the log
        last_idx = len(self.logs)
        try:
            while True:
                if last_idx < len(self.logs):
                    for idx in range(last_idx, len(self.logs)):
                        yield f"data: {json.dumps(self.logs[idx])}\n\n"
                    last_idx = len(self.logs)
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

streamer = LogStreamer()
