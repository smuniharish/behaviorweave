"""Shared pytest configuration: Hypothesis profiles.

Select a profile with the ``HYPOTHESIS_PROFILE`` environment variable (``dev`` by default).
CI uses ``ci``: more examples, derandomized for reproducible runs, and no per-example deadline
so slow shared runners cannot cause flaky failures.
"""

import os

from hypothesis import settings

settings.register_profile("dev", max_examples=100, deadline=None)
settings.register_profile("ci", max_examples=300, deadline=None, derandomize=True, print_blob=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
