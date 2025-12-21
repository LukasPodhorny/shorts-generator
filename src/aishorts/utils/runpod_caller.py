import os
import runpod


class EndpointCaller:
    def __init__(self, endpoint_id: str, timeout: int, api_key: str | None = None):
        runpod.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        self.endpoint = runpod.Endpoint(endpoint_id)
        self.timeout = timeout

    async def run_async(self, data: dict):
        run_request = self.endpoint.run(data)

        return run_request.output(timeout=self.timeout)
