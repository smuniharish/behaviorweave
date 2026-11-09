# Installation

BehaviorWeave supports Python 3.12 through 3.15.

```bash
uv add behaviorweave
```

Or install with `pip install behaviorweave`. LangChain, LangGraph, and agxai are installed
with the package; database drivers and model providers are application choices.

## Async execution

I/O boundaries are asynchronous: await engine processing, store operations, audit writes,
middleware halt inspection and release, and lifecycle methods. Pure policies, event adapters,
and state-transform callbacks remain synchronous.

Snippets use `await` inside your application's async function (or a notebook). For a script,
use `asyncio.run(main())`; use a selector event loop on Windows when running psycopg.

Continue with the [quickstart](quickstart.md), [examples](../examples/index.md), or
[customization inventory](../integrations/agxai.md#customization).
