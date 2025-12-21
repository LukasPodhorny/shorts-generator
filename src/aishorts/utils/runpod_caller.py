import os
import asyncio
import runpod


class EndpointCaller:
    def __init__(self, endpoint_id: str, timeout: int, api_key: str | None = None):
        runpod.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        self.endpoint = runpod.Endpoint(endpoint_id)
        self.timeout = timeout

    async def run_async(self, data: dict, poll_interval: float = 2.0):
        run_request = self.endpoint.run(data)

        total_wait = 0.0
        while True:
            status = run_request.status()

            if status == "COMPLETED":
                return run_request.output()
            elif status in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"RunPod job {status}")
            elif total_wait >= self.timeout:
                raise TimeoutError("RunPod job timed out")

            await asyncio.sleep(poll_interval)
            total_wait += poll_interval
