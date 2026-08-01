"""Centralized generation-model settings for Archivist.

The interactive application can use an official named model while the project is
being developed. A formal run of record has a stricter contract: its generator
and judge must be dated snapshots. Keep those concerns separate so a convenient
development default cannot be mistaken for a reproducible evaluation pin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal


ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]
Verbosity = Literal["low", "medium", "high"]

GPT_5_6_SOL_MODEL = "gpt-5.6-sol"
_DATED_SNAPSHOT_SUFFIX = re.compile(r"-(\d{4}-\d{2}-\d{2})$")


@dataclass(frozen=True, slots=True)
class ResponseModelSettings:
    """One generation role and the explicit settings sent to Responses."""

    role: str
    model: str
    reasoning_effort: ReasoningEffort
    verbosity: Verbosity

    def responses_create_kwargs(self) -> dict[str, object]:
        """Return a fresh request fragment in Responses API field shape."""
        return {
            "model": self.model,
            "reasoning": {"effort": self.reasoning_effort},
            "text": {"verbosity": self.verbosity},
        }

    @property
    def run_of_record_eligible(self) -> bool:
        """Whether the configured model meets the dated-snapshot contract."""
        return is_dated_model_snapshot(self.model)

    def require_run_of_record_snapshot(self) -> str:
        """Return the model or reject it before a formal evaluation run."""
        return require_dated_model_snapshot(self.model, role=self.role)


# The prior gpt-5 integration omitted both settings; its effective defaults were
# medium reasoning and medium verbosity. Making those values explicit preserves
# that baseline while preventing future model-default changes from moving it.
GENERATOR_SETTINGS = ResponseModelSettings(
    role="generator",
    model=GPT_5_6_SOL_MODEL,
    reasoning_effort="medium",
    verbosity="medium",
)

FOLLOWUP_RESOLVER_SETTINGS = ResponseModelSettings(
    role="follow-up resolver",
    model=GPT_5_6_SOL_MODEL,
    reasoning_effort="medium",
    verbosity="medium",
)

QUERY_PLANNER_SETTINGS = ResponseModelSettings(
    role="query planner",
    model=GPT_5_6_SOL_MODEL,
    reasoning_effort="low",
    verbosity="low",
)

# A distinct object from GENERATOR_SETTINGS holding identical values. Separate so
# full-context generation can be retuned later without silently moving the RAG
# cohort; identical at launch so a RAG-versus-full-context comparison holds the
# model snapshot, reasoning effort, and verbosity constant across arms.
FULL_CONTEXT_GENERATOR_SETTINGS = ResponseModelSettings(
    role="full-context generator",
    model=GPT_5_6_SOL_MODEL,
    reasoning_effort="medium",
    verbosity="medium",
)


def is_dated_model_snapshot(model: str) -> bool:
    """Return true only for a model identifier ending in a valid ISO date."""
    match = _DATED_SNAPSHOT_SUFFIX.search(model)
    if match is None:
        return False
    try:
        date.fromisoformat(match.group(1))
    except ValueError:
        return False
    return True


def require_dated_model_snapshot(model: str, *, role: str) -> str:
    """Enforce the locked run-of-record rule without inventing a snapshot ID."""
    if not is_dated_model_snapshot(model):
        raise ValueError(
            f"{role} model {model!r} is not a dated snapshot; "
            "formal runs of record require a model identifier ending in YYYY-MM-DD"
        )
    return model
