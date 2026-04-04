from __future__ import annotations

from enum import Enum


class CriteriaType(str, Enum):
    accuracy = "accuracy"
    completeness = "completeness"
    clarity = "clarity"
