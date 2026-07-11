from __future__ import annotations

from pid_decomposer_4d import PIDDecomposer4D
from pid_decomposer_5d import PIDDecomposer5D
from pid_decomposer_shared import DecompositionResult


def normalize_pid_mode(raw_mode: str) -> str:
    mode = str(raw_mode or "").strip()
    if mode in {"baseline_4d", "diag_5d", "full_5d"}:
        return mode
    return "baseline_4d"


def create_pid_decomposer(config: dict):
    pid_config = config.get("pid_decomposer", {})
    mode_name = normalize_pid_mode(pid_config.get("mode", "baseline_4d"))
    if mode_name == "baseline_4d":
        return PIDDecomposer4D(config, mode_name=mode_name)
    return PIDDecomposer5D(config, mode_name=mode_name)


class PIDDecomposer:
    """Thin selector facade for the concrete 4D/5D decomposers."""

    def __init__(self, config: dict):
        self.config = config
        self._impl = create_pid_decomposer(config)
        self.mode_name = self._impl.mode_name

    def __getattr__(self, name: str):
        return getattr(self._impl, name)

    def decompose_sample(self, sample):
        return self._impl.decompose_sample(sample)

    def decompose_day(self, level2_window):
        return self._impl.decompose_day(level2_window)
