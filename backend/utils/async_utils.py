import asyncio
from functools import wraps
from flask import current_app


def inti_async(app):
    pass


def async_route(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return current_app.async_task(f(*args, **kwargs))
    return wrapper
