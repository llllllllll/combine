import datetime


class _Expired(Exception):
    """Exception raised to indicate that a cache item has expired.
    """


class _Entry:
    """An expiring cache item.

    Parameters
    ----------
    value : any
        The value of the cache entry.
    expiring : datetime.datetime
        The time when this item should expire.
    """
    def __init__(self, value, expires):
        self._value = value
        self._expires = expires

    def __call__(self):
        if datetime.datetime.now() >= self._expires:
            raise _Expired()
        return self._value


class ExpiringCache:
    """A mapping from keys to values with an expiration datetime.
    """
    def __init__(self):
        self._entries = {}

    def __setitem__(self, key, value_expires):
        self._entries[key] = _Entry(*value_expires)

    def __getitem__(self, key):
        try:
            return self._entries[key]()
        except _Expired:
            raise KeyError(key)
