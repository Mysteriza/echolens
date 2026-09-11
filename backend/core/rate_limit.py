"""Shared slowapi limiter (single instance so limits apply process-wide)."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
