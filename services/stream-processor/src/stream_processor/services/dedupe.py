from datetime import datetime, timedelta


class DedupeCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._items: dict[str, datetime] = {}

    def seen(self, key: str, now: datetime) -> bool:
        expiry = self._items.get(key)
        if expiry and expiry > now:
            return True
        self._items[key] = now + self.ttl
        return False

    def cleanup(self, now: datetime) -> None:
        expired = [key for key, expiry in self._items.items() if expiry <= now]
        for key in expired:
            self._items.pop(key, None)
