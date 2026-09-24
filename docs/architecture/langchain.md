# LangChain integration

BehaviorWeave targets LangChain v1 as a mandatory runtime dependency. Applications can
construct agents with the public `langchain.agents.create_agent` API and feed callback
observations into `LangChainEventAdapter`, which accepts public callback-level observations for tool starts,
tool errors, and retries. It does not monkey-patch LangChain or depend on provider
packages. LangChain v1 agent construction remains the application's responsibility.
