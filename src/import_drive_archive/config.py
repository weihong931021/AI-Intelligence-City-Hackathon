"""Validated configuration values for safe archive processing."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SafetyLimits:
    """Hard limits applied before any archive content is extracted."""

    max_single_file_bytes: int = 1_073_741_824
    max_total_uncompressed_bytes: int = 10_737_418_240
    max_entry_count: int = 100_000
    max_compression_ratio: float = 1_000.0

    def __post_init__(self) -> None:
        integer_limits = (
            ("max_single_file_bytes", self.max_single_file_bytes),
            ("max_total_uncompressed_bytes", self.max_total_uncompressed_bytes),
            ("max_entry_count", self.max_entry_count),
        )
        for name, value in integer_limits:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        ratio = self.max_compression_ratio
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
            raise ValueError("max_compression_ratio must be a positive finite number")
        if not isfinite(ratio) or ratio <= 0:
            raise ValueError("max_compression_ratio must be a positive finite number")

    def to_dict(self) -> dict[str, int | float]:
        return {
            "max_single_file_bytes": self.max_single_file_bytes,
            "max_total_uncompressed_bytes": self.max_total_uncompressed_bytes,
            "max_entry_count": self.max_entry_count,
            "max_compression_ratio": self.max_compression_ratio,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SafetyLimits":
        return cls(**dict(data))
