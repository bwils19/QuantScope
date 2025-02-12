from datetime import datetime, timedelta
import asyncio
import redis
from contextlib import asynccontextmanager


class AlphaVantageRateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
        # Premium API limits - i don't think there actually are any... if so, this may be an unnecessary class
        self.calls_per_minute = 75
        # self.calls_per_day = 5000
        self.redis_key_minute = "av_calls_minute"
        self.redis_key_day = "av_calls_day"

    @asynccontextmanager
    async def request_limit(self):
        try:
            await self.check_and_wait()
            yield
        finally:
            # Update call counts
            pipe = self.redis.pipeline()
            now = datetime.now()
            pipe.incr(self.redis_key_minute)
            pipe.expire(self.redis_key_minute, 60)
            pipe.incr(self.redis_key_day)
            pipe.expire(self.redis_key_day, 86400)
            pipe.execute()

    async def check_and_wait(self):
        while True:
            minute_calls = int(self.redis.get(self.redis_key_minute) or 0)
            day_calls = int(self.redis.get(self.redis_key_day) or 0)

            if minute_calls >= self.calls_per_minute:
                await asyncio.sleep(5)  # Wait and check again
                continue
            # if day_calls >= self.calls_per_day:
            #     raise Exception("Daily API limit reached")
            break


rate_limiter = AlphaVantageRateLimiter(redis.Redis())

