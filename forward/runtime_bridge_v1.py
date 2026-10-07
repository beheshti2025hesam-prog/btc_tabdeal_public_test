"""Branch-safe bridge from Forward Run Controller to the existing pipeline/journal."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .forward_run_controller_v1 import ForwardRunControllerV1
from .forward_pipeline_v1 import ForwardPipelineV1


class ForwardRuntimeBridgeV1:
    def __init__(
        self,
        *,
        controller: ForwardRunControllerV1,
        pipeline: ForwardPipelineV1,
    ) -> None:
        self.controller = controller
        self.pipeline = pipeline

    def prepare_run(
        self,
        *,
        run_id: str,
        observed_at: datetime,
    ):
        return self.controller.start(
            run_id=run_id,
            observed_at=observed_at,
            inputs=[],
        )

    def process_input(
        self,
        *,
        run_id: str,
        observed_at: datetime,
        market_input: Any,
        **kwargs: Any,
    ):
        status = self.prepare_run(run_id=run_id, observed_at=observed_at)
        if status.status != "READY":
            return status

        # Pipeline wiring is explicit. The bridge never supplies hidden policy.
        return self.pipeline.run_once(
            market_input=market_input,
            **kwargs,
        )
