"""Startup-only exposure profiles for local development and the public demo."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


class ExposureProfile(StrEnum):
    DEVELOPMENT = "development"
    PUBLIC_DEMO = "public_demo"


class ExposureConfigurationError(ValueError):
    """Raised when a startup profile would create an unsafe public service."""


def _positive_int(environment: dict[str, str], name: str, default: int) -> int:
    raw_value = environment.get(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ExposureConfigurationError(f"{name} must be an integer") from exc
    if value < 1:
        raise ExposureConfigurationError(f"{name} must be at least 1")
    return value


@dataclass(frozen=True, slots=True)
class ExposureSettings:
    profile: ExposureProfile
    data_root: Path
    locator_artifact: Path
    public_monthly_budget_usd: Decimal | None = None
    public_requests_per_minute: int = 6
    public_global_requests_per_minute: int = 20
    public_max_concurrent_requests: int = 1
    public_max_concurrent_per_client: int = 1
    public_n_results: int = 5
    public_max_request_bytes: int = 24_000

    @property
    def is_public(self) -> bool:
        return self.profile is ExposureProfile.PUBLIC_DEMO

    @classmethod
    def development(cls) -> "ExposureSettings":
        return cls(
            profile=ExposureProfile.DEVELOPMENT,
            data_root=BASE_DIR,
            locator_artifact=(
                BASE_DIR
                / "fixtures"
                / "edition_locators"
                / "typeset_pdf_0706.json"
            ),
        )

    @classmethod
    def public_demo(
        cls,
        *,
        monthly_budget_usd: Decimal | str,
        data_root: Path = BASE_DIR,
        locator_artifact: Path | None = None,
        requests_per_minute: int = 6,
        global_requests_per_minute: int = 20,
        max_concurrent_requests: int = 1,
        max_concurrent_per_client: int = 1,
        n_results: int = 5,
        max_request_bytes: int = 24_000,
    ) -> "ExposureSettings":
        try:
            budget = Decimal(str(monthly_budget_usd))
        except InvalidOperation as exc:
            raise ExposureConfigurationError(
                "public monthly budget must be a decimal amount"
            ) from exc
        if not budget.is_finite() or budget <= 0:
            raise ExposureConfigurationError("public monthly budget must be greater than zero")
        positive_values = {
            "requests_per_minute": requests_per_minute,
            "global_requests_per_minute": global_requests_per_minute,
            "max_concurrent_requests": max_concurrent_requests,
            "max_concurrent_per_client": max_concurrent_per_client,
            "n_results": n_results,
            "max_request_bytes": max_request_bytes,
        }
        invalid = [name for name, value in positive_values.items() if value < 1]
        if invalid:
            raise ExposureConfigurationError(
                f"public limits must be positive: {', '.join(invalid)}"
            )
        if n_results > 12:
            raise ExposureConfigurationError("public n_results may not exceed 12")
        return cls(
            profile=ExposureProfile.PUBLIC_DEMO,
            data_root=data_root.resolve(),
            locator_artifact=(
                locator_artifact
                or BASE_DIR
                / "fixtures"
                / "edition_locators"
                / "typeset_pdf_0706.json"
            ).resolve(),
            public_monthly_budget_usd=budget,
            public_requests_per_minute=requests_per_minute,
            public_global_requests_per_minute=global_requests_per_minute,
            public_max_concurrent_requests=max_concurrent_requests,
            public_max_concurrent_per_client=max_concurrent_per_client,
            public_n_results=n_results,
            public_max_request_bytes=max_request_bytes,
        )

    @classmethod
    def from_env(
        cls,
        environment: dict[str, str] | None = None,
    ) -> "ExposureSettings":
        env = dict(os.environ if environment is None else environment)
        raw_profile = env.get(
            "ARCHIVIST_EXPOSURE_PROFILE",
            ExposureProfile.DEVELOPMENT.value,
        ).strip()
        try:
            profile = ExposureProfile(raw_profile)
        except ValueError as exc:
            choices = ", ".join(item.value for item in ExposureProfile)
            raise ExposureConfigurationError(
                f"ARCHIVIST_EXPOSURE_PROFILE must be one of: {choices}"
            ) from exc

        data_root = Path(env.get("ARCHIVIST_DATA_ROOT", str(BASE_DIR))).expanduser()
        raw_locator = env.get("ARCHIVIST_EDITION_LOCATORS_PATH", "").strip()
        locator = (
            Path(raw_locator).expanduser()
            if raw_locator
            else BASE_DIR
            / "fixtures"
            / "edition_locators"
            / "typeset_pdf_0706.json"
        )
        if profile is ExposureProfile.DEVELOPMENT:
            return cls(
                profile=profile,
                data_root=data_root.resolve(),
                locator_artifact=locator.resolve(),
            )

        raw_budget = env.get("ARCHIVIST_PUBLIC_MONTHLY_BUDGET_USD", "").strip()
        if not raw_budget:
            raise ExposureConfigurationError(
                "ARCHIVIST_PUBLIC_MONTHLY_BUDGET_USD is required in public_demo mode"
            )
        return cls.public_demo(
            monthly_budget_usd=raw_budget,
            data_root=data_root,
            locator_artifact=locator,
            requests_per_minute=_positive_int(
                env,
                "ARCHIVIST_PUBLIC_REQUESTS_PER_MINUTE",
                6,
            ),
            global_requests_per_minute=_positive_int(
                env,
                "ARCHIVIST_PUBLIC_GLOBAL_REQUESTS_PER_MINUTE",
                20,
            ),
            max_concurrent_requests=_positive_int(
                env,
                "ARCHIVIST_PUBLIC_MAX_CONCURRENT_REQUESTS",
                1,
            ),
            max_concurrent_per_client=_positive_int(
                env,
                "ARCHIVIST_PUBLIC_MAX_CONCURRENT_PER_CLIENT",
                1,
            ),
            n_results=_positive_int(env, "ARCHIVIST_PUBLIC_N_RESULTS", 5),
            max_request_bytes=_positive_int(
                env,
                "ARCHIVIST_PUBLIC_MAX_REQUEST_BYTES",
                24_000,
            ),
        )
