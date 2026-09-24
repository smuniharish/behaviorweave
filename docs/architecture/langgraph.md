# LangGraph integration

`LangGraphEventAdapter` normalizes node and tool observations. It does not route,
interrupt, persist, or execute decisions. The host can translate `STOP`, `PAUSE`, or
`REDIRECT` into its graph-specific control flow.
