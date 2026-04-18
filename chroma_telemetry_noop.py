"""No-op Chroma telemetry to avoid Posthog capture() signature errors."""
from overrides import override

from chromadb.config import System
from chromadb.telemetry.product import ProductTelemetryClient, ProductTelemetryEvent


class NoOpProductTelemetryClient(ProductTelemetryClient):
    """Telemetry client that does nothing (avoids posthog version bugs)."""

    def __init__(self, system: System) -> None:
        super().__init__(system)

    @override
    def capture(self, event: ProductTelemetryEvent) -> None:
        pass