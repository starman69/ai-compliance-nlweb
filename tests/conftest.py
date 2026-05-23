"""Test session config.

The app defaults to NLWEB_BACKEND=real (live local models). Tests/CI run fully
offline, so pin the Mock backend here unless a test overrides it. This is the
only place Mock is the default — the running app uses real models.
"""
import os

os.environ.setdefault("NLWEB_BACKEND", "mock")
