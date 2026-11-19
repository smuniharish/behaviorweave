<div align="center">

# BehaviorWeave

**Async behavioral policies and interventions for LangGraph and LangChain agents.**

[![CI](https://github.com/smuniharish/behaviorweave/actions/workflows/ci.yml/badge.svg)](https://github.com/smuniharish/behaviorweave/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/behaviorweave.svg)](https://pypi.org/project/behaviorweave/)
[![Python](https://img.shields.io/pypi/pyversions/behaviorweave.svg)](https://pypi.org/project/behaviorweave/)
[![Docs](https://readthedocs.org/projects/behaviorweave/badge/?version=latest)](https://behaviorweave.readthedocs.io/en/latest/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/smuniharish/behaviorweave/blob/master/LICENSE)

</div>

Agents repeat tool calls, retry failing dependencies, and bounce work between specialists.
BehaviorWeave detects these patterns deterministically and returns typed interventions:
your application decides when to nudge, escalate, request review, or stop.

![BehaviorWeave architecture](https://raw.githubusercontent.com/smuniharish/behaviorweave/master/docs/assets/diagrams/architecture.png)

## Highlights

- **Deterministic and explainable:** pattern, count, threshold, policy, and provenance;
  no model call is needed to evaluate a policy.
- **Async-first:** engine, storage, audit, and lifecycle operations are awaitable.
- **LangChain middleware:** guard `create_agent` and Deep Agents tool calls; scope by thread,
  append guidance, block configured kinds, and track outcomes.
- **Customizable:** ABCs for patterns, stores, and sinks; inject every agxai capability,
  plugin, configuration, and exporter.
- **Durable history:** LangGraph BaseStore adapter and PostgreSQL/Redis reference stores;
  persisted middleware halts and reusable conformance tests.
- **Reliable:** scope isolation, idempotent redelivery, atomic state transitions, and
  100% source line and branch coverage.

## Install

```bash
pip install behaviorweave
```

Or `uv add behaviorweave`. Supports Python 3.12 through 3.15.

## Downloads

<p>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520sum%2528count%2529%2520v%2520FROM%2520pypi.pypi_downloads_per_day%2520WHERE%2520project%253D%2527behaviorweave%2527%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=downloads&amp;color=blue&amp;cacheSeconds=3600" alt="Total downloads"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520sum%2528count%2529%2520v%2520FROM%2520pypi.pypi_downloads_per_day%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520date%2520%253E%253D%2520toStartOfWeek%2528toDate%2528now%2528%2527UTC%2527%2529%2529%252C%25201%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=this%20week&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads this week"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520sum%2528count%2529%2520v%2520FROM%2520pypi.pypi_downloads_per_day%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520date%2520%253E%253D%2520toStartOfMonth%2528toDate%2528now%2528%2527UTC%2527%2529%2529%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=this%20month&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads this month"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520sum%2528count%2529%2520v%2520FROM%2520pypi.pypi_downloads_per_day%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520date%2520%253E%253D%2520toStartOfYear%2528toDate%2528now%2528%2527UTC%2527%2529%2529%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=this%20year&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads this year"></a>
</p>
<p>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520arrayStringConcat%2528groupArray%2528concat%2528toString%2528y%2529%252C%2520%2527%253A%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2520v%2520FROM%2520%2528SELECT%2520toYear%2528date%2529%2520y%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day%2520WHERE%2520project%253D%2527behaviorweave%2527%2520GROUP%2520BY%2520y%2520ORDER%2520BY%2520y%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=by%20year&amp;color=blue&amp;cacheSeconds=3600" alt="Downloads by year"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527A%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20A&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries A"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527B%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20B&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries B"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527C%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20C&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries C"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527D%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20D&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries D"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527E%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20E&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries E"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527F%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20F&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries F"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527G%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20G&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries G"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527H%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20H&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries H"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527I%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20I&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries I"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527J%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20J&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries J"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527K%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20K&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries K"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527L%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20L&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries L"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527M%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20M&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries M"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527N%2527%252C%2520%2527O%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20N-O&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries N-O"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527P%2527%252C%2520%2527Q%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20P-Q&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries P-Q"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527R%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20R&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries R"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527S%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20S&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries S"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527T%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20T&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries T"></a>
  <a href="https://clickpy.clickhouse.com/dashboard/behaviorweave"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fuser%3Ddemo%26query%3DSELECT%2520if%2528empty%2528groupArray%2528c%2529%2529%252C%2520%2527none%2527%252C%2520arrayStringConcat%2528groupArray%2528concat%2528if%2528empty%2528ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527unknown%2527%252C%2520ifNull%2528country_code%252C%2520%2527%2527%2529%2529%252C%2520%2527%2520%2527%252C%2520toString%2528c%2529%2529%2529%252C%2520%2527%2520%257C%2520%2527%2529%2529%2520v%2520FROM%2520%2528SELECT%2520country_code%252C%2520sum%2528count%2529%2520c%2520FROM%2520pypi.pypi_downloads_per_day_by_version_by_country%2520WHERE%2520project%253D%2527behaviorweave%2527%2520AND%2520substring%2528ifNull%2528country_code%252C%2520%2527%2527%2529%252C%25201%252C%25201%2529%2520IN%2520%2528%2527U%2527%252C%2520%2527V%2527%252C%2520%2527W%2527%252C%2520%2527X%2527%252C%2520%2527Y%2527%252C%2520%2527Z%2527%2529%2520GROUP%2520BY%2520country_code%2520ORDER%2520BY%2520c%2520DESC%252C%2520country_code%2529%2520FORMAT%2520JSON&amp;query=%24.data%5B0%5D.v&amp;label=countries%20U-Z&amp;color=blue&amp;cacheSeconds=3600" alt="Download countries U-Z"></a>
</p>

Download counts come from the [ClickHouse public PyPI dataset](https://clickpy.clickhouse.com/dashboard/behaviorweave),
which refreshes daily, so counts may be about a day behind. Shields caches badge images for
up to an hour, and GitHub may also cache them. Weeks start on Monday (UTC). Explore
interactive charts on the [ClickPy dashboard](https://clickpy.clickhouse.com/dashboard/behaviorweave).

## Quickstart

```python
import asyncio
from behaviorweave import BehaviorEngine, BehaviorEvent, InterventionType, PolicyRule


async def main():
    async with BehaviorEngine(
        policies=[
            PolicyRule("nudge", "repeated_tool_call", 2, InterventionType.NUDGE),
            PolicyRule("stop", "repeated_tool_call", 3, InterventionType.STOP),
        ]
    ) as engine:
        kinds = []
        for _ in range(3):
            decision = await engine.process(
                BehaviorEvent.tool_call("get_alarm", {"machine": "ETCH-3"}, scope="incident-42")
            )
            kinds.append(decision.intervention.kind.value)
        print(kinds)  # ['noop', 'nudge', 'stop']


asyncio.run(main())
```

### Guard a LangChain agent

<!-- skip-snippet: requires a configured provider-backed model and application tools -->
```python
from langchain.agents import create_agent
from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware

agent = create_agent(model, tools=[get_alarm], middleware=[BehaviorWeaveMiddleware(engine)])
result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Inspect ETCH-3."}]},
    config={"configurable": {"thread_id": "incident-42"}},
)
```

The second identical call receives `[BehaviorWeave:nudge]` guidance. The third is blocked
before the tool runs. The engine returns decisions; enforcement belongs to the middleware
or your host application.

## Built-in patterns

| Pattern | Detects |
| --- | --- |
| `repeated_tool_call` | Consecutive identical tool calls. |
| `repeated_node_execution` | Consecutive executions of one node. |
| `failure_streak`, `retry_streak`, `success_streak` | Consecutive outcomes. |
| `delegation_streak` | Repeated delegation to one agent. |
| `oscillation` | Back-and-forth handoffs or delegations. |
| `event_frequency` | Total occurrences of each event identity. |

Policies select thresholds, priorities, per-policy cooldowns, once-only behavior, and
intervention kinds. Configure the built-in pattern classes or subclass the `Pattern` ABC.

## Integrations and customization

| Surface | Available customization |
| --- | --- |
| LangChain | Scope, block kinds, sync/async decision hook, formatter, middleware name. |
| LangGraph | Host-owned routing/checkpoints, event adapters, BaseStore namespace and TTL. |
| agxai | Config, registry, identity, plugins, custom capture, store, exporter, attribution, explanation, disclosure and capture policies. |
| Audit | Async `AuditSink`, in-memory sink, `CompositeAuditSink` fan-out, and `AgxaiAuditSink` for semantic decisions. |
| Metrics | `OpenTelemetryMetricsSink` counts decisions on any `MeterProvider` (`otel` extra). |
| Storage | Async `BehaviorStateStore` ABC with scope release, and PostgreSQL/Redis reference implementations. |
| MCP / Swarm / Deep Agents | Guards at real tool, delegation, and handoff boundaries. |

See the [downstream inventory](https://behaviorweave.readthedocs.io/en/latest/integrations/compatibility/).
agxai is used for provenance and explanations; BehaviorWeave owns behavioral decisions.

## Examples and Agent Skills

The [twenty async examples](https://github.com/smuniharish/behaviorweave/tree/master/examples)
cover middleware, MCP, graph loops, Swarm, Deep Agents, concurrent runs, durable databases,
agxai semantic audit, OpenTelemetry traces and metrics, and batch replay. Configure model credentials through environment
variables; database/OTel examples support local Podman services.

The [Agent Skills](https://github.com/smuniharish/behaviorweave/tree/master/behaviorweave-skills)
teach agents how to integrate and extend the package, with executable checks and evaluations.

## Documentation and project

- [Quickstart](https://behaviorweave.readthedocs.io/en/latest/getting-started/quickstart/)
- [Concepts](https://behaviorweave.readthedocs.io/en/latest/guide/concepts/events/)
- [Integrations](https://behaviorweave.readthedocs.io/en/latest/integrations/langchain/)
- [API reference](https://behaviorweave.readthedocs.io/en/latest/api/)
- [Changelog](https://github.com/smuniharish/behaviorweave/blob/master/CHANGELOG.md)
- [Contributing](https://github.com/smuniharish/behaviorweave/blob/master/CONTRIBUTING.md)
- [Code of Conduct](https://github.com/smuniharish/behaviorweave/blob/master/CODE_OF_CONDUCT.md)
- [Security](https://github.com/smuniharish/behaviorweave/blob/master/SECURITY.md)

Apache License 2.0. See [LICENSE](https://github.com/smuniharish/behaviorweave/blob/master/LICENSE).
