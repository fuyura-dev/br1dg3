"""Shared generation and transport policy for both repair methods."""

GENERATION_CONFIG = {"thinking_level": "minimal"}

# The pinned Interactions SDK retry configuration is disabled in create_client().
# Keep retries observable in llm.py (one initial attempt plus three).
MAX_RETRIES = 3
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_ERRORS = {"ReadTimeout", "ConnectTimeout", "ConnectError", "TimeoutException",
                "RemoteProtocolError", "NoResponseError", "APITimeoutError", "APIConnectionError"}


def retry_delay(retry_index):
    return 2 ** retry_index  # 1, 2, 4 seconds before application retries.
