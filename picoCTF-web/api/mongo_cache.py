"""Legacy Caching Library based on mongodb collection."""

import datetime
import logging
from functools import wraps

import api
from api import PicoException

log = logging.getLogger(__name__)


def _get_hash_key(f, args, kwargs):
    """
    Return a hash for a given function invocation.

    Args:
        f: the function
        args: positional arguments (list)
        kwargs: keyword arguments (dict)

    Returns:
        a hashed key (int), or None if any argument was unhashable

    """
    try:
        return hash((f.__module__, f.__name__,
                    tuple(args),
                    tuple(sorted(kwargs.items()))))
    except TypeError:
        return None


def _get(key):
    """
    Get a result from the cache.

    Args:
        key: cache key
    Returns:
        The result from the cache, or None
    """
    db = api.db.get_conn()
    cached_result = db.cache.find_one({'key': key})

    if cached_result:
        return cached_result["value"]


def _set(key, value, timeout=None):
    """
    Set a key in the cache.

    Args:
        key: The cache key
        timeout: Time the key is valid (seconds)
    """
    db = api.db.get_conn()
    cache_obj = {
        '$set': {
            'key': key,
            'value': value,
        }
    }

    if timeout is not None:
        cache_obj['$set']['expireAt'] = (
            datetime.datetime.now() + datetime.timedelta(seconds=timeout))
    db.cache.find_one_and_update({'key': key}, cache_obj, upsert=True)


def memoize(*args, **kwargs):
    """
    Memoize a function by caching its results.

    To force a cache update, set the kwarg 'recache=True' when calling
    the decorated function.

    Function calls containing unhashable arguments will not be cached.

    Args (optionally specify as kwargs to the decorator):
        timeout: Time the result stays valid in the cache (seconds, default 60)
    Returns:
        The function's result.

    """
    # Allow use of decorator without () if no kwargs specified
    f = None
    if len(args) == 1 and callable(args[0]):
        f = args[0]
    timeout = kwargs.get('timeout', 60)

    def decorator(f):
        """Inner decorator."""
        @wraps(f)
        def wrapper(*args, **kwargs):
            """Cache a function result."""
            # Force a cache update if the "recache" kwarg is provided
            if kwargs.get('recache', None) is not None:
                kwargs.pop('recache', None)
                key = _get_hash_key(f, args, kwargs)
                function_result = f(*args, **kwargs)
                _set(key, function_result, timeout=timeout)
                return function_result

            key = _get_hash_key(f, args, kwargs)
            if key is None:
                # Invokation contains an unhashable argument
                return f(*args, **kwargs)
            cached_result = _get(key)
            if cached_result is None:
                function_result = f(*args, **kwargs)
                _set(key, function_result, timeout=timeout)
                return function_result
            return cached_result
        return wrapper
    return decorator(f) if f else decorator


def clear():
    """Clear the cache."""
    db = api.db.get_conn()
    db.cache.remove()
