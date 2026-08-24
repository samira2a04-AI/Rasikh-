"""FastAPI API layer for the Rasikh Legal Platform.

This layer is a thin HTTP boundary: it validates requests, delegates to the
deterministic services in ``app.services`` (via the thin orchestrator in
``app.services.workflow``), owns each request's transaction, and translates
service-level exceptions into sensible HTTP responses. No business or
authorization logic lives here.
"""
