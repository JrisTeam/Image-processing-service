import time
from uuid import UUID

RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 60  # seconds


def check_rate_limit(user_id: UUID, redis_client) -> tuple[bool, int]:
    """
    Sliding window rate limiter using a Redis sorted set.

    Returns (True, 0) if the request is allowed.
    Returns (False, retry_after_seconds) if the limit is exceeded.
    """
    key = f"rate_limit:{user_id}"
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW

    # Remove entries older than the 60-second window
    redis_client.zremrangebyscore(key, "-inf", window_start)

    # Count remaining entries in the window
    count = redis_client.zcard(key)

    if count < RATE_LIMIT_REQUESTS:
        # Add current request timestamp as both score and member (unique via now)
        redis_client.zadd(key, {str(now): now})
        redis_client.expire(key, RATE_LIMIT_WINDOW)
        return (True, 0)
    else:
        # Find the oldest entry to compute retry_after
        oldest = redis_client.zrange(key, 0, 0, withscores=True)
        if oldest:
            oldest_timestamp = oldest[0][1]
            retry_after = int(RATE_LIMIT_WINDOW - (now - oldest_timestamp))
            retry_after = max(1, retry_after)
        else:
            retry_after = RATE_LIMIT_WINDOW
        return (False, retry_after)
