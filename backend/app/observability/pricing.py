from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from fnmatch import fnmatchcase

from app.storage.models import ModelPricingModel

PRICING_VERSION = "v1"


@dataclass(frozen=True)
class PricingMatchResult:
    pricing_id: str | None
    pricing_match_rule: str | None
    pricing_version: str | None
    input_price_nano_usd_per_million: int | None
    output_price_nano_usd_per_million: int | None
    cached_input_price_nano_usd_per_million: int | None
    match_status: str


@dataclass(frozen=True)
class PricingComputationResult:
    pricing_id: str | None
    pricing_match_rule: str | None
    pricing_version: str | None
    input_price_nano_usd_per_million: int | None
    output_price_nano_usd_per_million: int | None
    cached_input_price_nano_usd_per_million: int | None
    input_cost_nano_usd: int | None
    output_cost_nano_usd: int | None
    cached_input_cost_nano_usd: int | None
    total_cost_nano_usd: int | None
    cost_status: str


class ModelPricingMatcher:
    def __init__(self, db) -> None:
        self.db = db

    def match(
        self,
        *,
        provider_id: str,
        model_id: str,
        started_at: datetime,
    ) -> PricingMatchResult:
        rows = self._load_candidates(
            provider_id=provider_id,
            started_at=started_at,
        )

        exact_rows = [
            row
            for row in rows
            if row["match_type"] == "exact" and row["model_pattern"] == model_id
        ]
        if exact_rows:
            return self._select_match(
                exact_rows,
                match_rule_prefix="exact",
            )

        pattern_rows = [
            row
            for row in rows
            if row["match_type"] == "pattern" and fnmatchcase(model_id, row["model_pattern"])
        ]
        if not pattern_rows:
            return PricingMatchResult(
                pricing_id=None,
                pricing_match_rule=None,
                pricing_version=None,
                input_price_nano_usd_per_million=None,
                output_price_nano_usd_per_million=None,
                cached_input_price_nano_usd_per_million=None,
                match_status="not_found",
            )

        highest_priority = max(row["priority"] for row in pattern_rows)
        top_rows = [row for row in pattern_rows if row["priority"] == highest_priority]
        return self._select_match(
            top_rows,
            match_rule_prefix="pattern",
        )

    def _load_candidates(
        self,
        *,
        provider_id: str,
        started_at: datetime,
    ) -> list[dict]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(ModelPricingModel)
                .filter(
                    ModelPricingModel.provider_id == provider_id,
                    ModelPricingModel.effective_from <= started_at,
                    (
                        (ModelPricingModel.effective_to.is_(None))
                        | (started_at < ModelPricingModel.effective_to)
                    ),
                )
                .all()
            )
            return [
                {
                    "id": model.id,
                    "model_pattern": model.model_pattern,
                    "match_type": model.match_type,
                    "priority": model.priority,
                    "input_price_nano_usd_per_million": (
                        model.input_price_nano_usd_per_million
                    ),
                    "output_price_nano_usd_per_million": (
                        model.output_price_nano_usd_per_million
                    ),
                    "cached_input_price_nano_usd_per_million": (
                        model.cached_input_price_nano_usd_per_million
                    ),
                }
                for model in models
            ]

    @staticmethod
    def _select_match(
        rows: list[dict],
        *,
        match_rule_prefix: str,
    ) -> PricingMatchResult:
        if len(rows) != 1:
            return PricingMatchResult(
                pricing_id=None,
                pricing_match_rule="pricing_ambiguous",
                pricing_version=PRICING_VERSION,
                input_price_nano_usd_per_million=None,
                output_price_nano_usd_per_million=None,
                cached_input_price_nano_usd_per_million=None,
                match_status="ambiguous",
            )

        row = rows[0]
        return PricingMatchResult(
            pricing_id=row["id"],
            pricing_match_rule=f"{match_rule_prefix}:{row['model_pattern']}",
            pricing_version=PRICING_VERSION,
            input_price_nano_usd_per_million=row["input_price_nano_usd_per_million"],
            output_price_nano_usd_per_million=row["output_price_nano_usd_per_million"],
            cached_input_price_nano_usd_per_million=row[
                "cached_input_price_nano_usd_per_million"
            ],
            match_status="matched",
        )


class ProviderRequestCostCalculator:
    def __init__(self, db) -> None:
        self.matcher = ModelPricingMatcher(db)

    def compute(
        self,
        *,
        provider_id: str,
        model_id: str,
        started_at: datetime,
        input_tokens: int | None,
        output_tokens: int | None,
        cached_input_tokens: int | None,
        estimated_input_tokens: int | None,
        estimated_output_tokens: int | None,
        input_usage_source: str,
        output_usage_source: str,
        cached_usage_source: str,
    ) -> PricingComputationResult:
        match = self.matcher.match(
            provider_id=provider_id,
            model_id=model_id,
            started_at=started_at,
        )
        if match.match_status != "matched":
            return PricingComputationResult(
                pricing_id=match.pricing_id,
                pricing_match_rule=match.pricing_match_rule,
                pricing_version=match.pricing_version,
                input_price_nano_usd_per_million=None,
                output_price_nano_usd_per_million=None,
                cached_input_price_nano_usd_per_million=None,
                input_cost_nano_usd=None,
                output_cost_nano_usd=None,
                cached_input_cost_nano_usd=None,
                total_cost_nano_usd=None,
                cost_status="unpriced",
            )

        input_cost = None
        output_cost = None
        cached_cost = None
        estimated_used = False
        unknown_usage = False

        cached_price = match.cached_input_price_nano_usd_per_million
        input_price = match.input_price_nano_usd_per_million
        output_price = match.output_price_nano_usd_per_million

        if output_price is not None:
            output_token_value, output_estimated, output_unknown = self._resolve_usage_value(
                direct_tokens=output_tokens,
                estimated_tokens=estimated_output_tokens,
                usage_source=output_usage_source,
            )
            if output_unknown:
                unknown_usage = True
            elif output_token_value is not None:
                output_cost = self._compute_cost(
                    output_token_value,
                    output_price,
                )
                estimated_used = estimated_used or output_estimated

        if input_price is not None:
            input_token_value, input_estimated, input_unknown = self._resolve_usage_value(
                direct_tokens=input_tokens,
                estimated_tokens=estimated_input_tokens,
                usage_source=input_usage_source,
            )
            if cached_price is not None:
                cached_token_value, cached_estimated, cached_unknown = self._resolve_usage_value(
                    direct_tokens=cached_input_tokens,
                    estimated_tokens=None,
                    usage_source=cached_usage_source,
                )
                if input_unknown or cached_unknown:
                    unknown_usage = True
                elif input_token_value is not None and cached_token_value is not None:
                    billable_input_tokens = max(input_token_value - cached_token_value, 0)
                    input_cost = self._compute_cost(
                        billable_input_tokens,
                        input_price,
                    )
                    cached_cost = self._compute_cost(
                        cached_token_value,
                        cached_price,
                    )
                    estimated_used = estimated_used or input_estimated or cached_estimated
            else:
                if input_unknown:
                    unknown_usage = True
                elif input_token_value is not None:
                    input_cost = self._compute_cost(
                        input_token_value,
                        input_price,
                    )
                    estimated_used = estimated_used or input_estimated

        total_cost = None
        known_costs = [
            value for value in (input_cost, output_cost, cached_cost) if value is not None
        ]
        if known_costs:
            total_cost = sum(known_costs)

        if unknown_usage:
            cost_status = "incomplete"
        elif estimated_used:
            cost_status = "estimated"
        else:
            cost_status = "exact"

        return PricingComputationResult(
            pricing_id=match.pricing_id,
            pricing_match_rule=match.pricing_match_rule,
            pricing_version=match.pricing_version,
            input_price_nano_usd_per_million=input_price,
            output_price_nano_usd_per_million=output_price,
            cached_input_price_nano_usd_per_million=cached_price,
            input_cost_nano_usd=input_cost,
            output_cost_nano_usd=output_cost,
            cached_input_cost_nano_usd=cached_cost,
            total_cost_nano_usd=total_cost,
            cost_status=cost_status,
        )

    @staticmethod
    def _resolve_usage_value(
        *,
        direct_tokens: int | None,
        estimated_tokens: int | None,
        usage_source: str,
    ) -> tuple[int | None, bool, bool]:
        if usage_source == "provider":
            return direct_tokens, False, direct_tokens is None
        if usage_source == "estimated":
            return estimated_tokens, True, estimated_tokens is None
        return None, False, True

    @staticmethod
    def _compute_cost(tokens: int, price_nano_usd_per_million: int) -> int:
        return (tokens * price_nano_usd_per_million + 500_000) // 1_000_000
