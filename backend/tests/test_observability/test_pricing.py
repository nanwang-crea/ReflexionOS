from datetime import UTC, datetime

from app.observability.pricing import ModelPricingMatcher, ProviderRequestCostCalculator
from app.storage.database import Database
from app.storage.models import ModelPricingModel


def _seed_price(
    db: Database,
    *,
    pricing_id: str,
    provider_id: str = "provider-openai",
    model_pattern: str = "gpt-4-turbo-preview",
    match_type: str = "exact",
    priority: int = 0,
    input_price: int | None = 1_000_000,
    output_price: int | None = 2_000_000,
    cached_price: int | None = 500_000,
) -> None:
    with db.get_session() as db_session:
        db_session.add(
            ModelPricingModel(
                id=pricing_id,
                provider_id=provider_id,
                model_pattern=model_pattern,
                match_type=match_type,
                priority=priority,
                input_price_nano_usd_per_million=input_price,
                output_price_nano_usd_per_million=output_price,
                cached_input_price_nano_usd_per_million=cached_price,
                currency="USD",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                effective_to=None,
            )
        )


def test_pricing_matcher_prefers_exact_match(tmp_path):
    db = Database(str(tmp_path / "pricing-exact.db"))
    _seed_price(
        db,
        pricing_id="pattern-price",
        model_pattern="gpt-*",
        match_type="pattern",
        priority=100,
    )
    _seed_price(
        db,
        pricing_id="exact-price",
        model_pattern="gpt-4-turbo-preview",
        match_type="exact",
    )

    result = ModelPricingMatcher(db).match(
        provider_id="provider-openai",
        model_id="gpt-4-turbo-preview",
        started_at=datetime(2026, 7, 26, tzinfo=UTC),
    )

    assert result.match_status == "matched"
    assert result.pricing_id == "exact-price"
    assert result.pricing_match_rule == "exact:gpt-4-turbo-preview"


def test_pricing_matcher_marks_same_priority_patterns_ambiguous(tmp_path):
    db = Database(str(tmp_path / "pricing-ambiguous.db"))
    _seed_price(
        db,
        pricing_id="pattern-a",
        model_pattern="gpt-4-*",
        match_type="pattern",
        priority=10,
    )
    _seed_price(
        db,
        pricing_id="pattern-b",
        model_pattern="gpt-*",
        match_type="pattern",
        priority=10,
    )

    result = ModelPricingMatcher(db).match(
        provider_id="provider-openai",
        model_id="gpt-4-turbo-preview",
        started_at=datetime(2026, 7, 26, tzinfo=UTC),
    )

    assert result.match_status == "ambiguous"
    assert result.pricing_id is None
    assert result.pricing_match_rule == "pricing_ambiguous"


def test_cost_calculator_computes_exact_cost_with_cached_tokens(tmp_path):
    db = Database(str(tmp_path / "pricing-cost.db"))
    _seed_price(db, pricing_id="exact-price")

    result = ProviderRequestCostCalculator(db).compute(
        provider_id="provider-openai",
        model_id="gpt-4-turbo-preview",
        started_at=datetime(2026, 7, 26, tzinfo=UTC),
        input_tokens=6,
        output_tokens=4,
        cached_input_tokens=2,
        estimated_input_tokens=None,
        estimated_output_tokens=None,
        input_usage_source="provider",
        output_usage_source="provider",
        cached_usage_source="provider",
    )

    assert result.cost_status == "exact"
    assert result.pricing_id == "exact-price"
    assert result.input_cost_nano_usd == 4
    assert result.output_cost_nano_usd == 8
    assert result.cached_input_cost_nano_usd == 1
    assert result.total_cost_nano_usd == 13


def test_cost_calculator_marks_missing_cached_usage_incomplete(tmp_path):
    db = Database(str(tmp_path / "pricing-incomplete.db"))
    _seed_price(db, pricing_id="exact-price")

    result = ProviderRequestCostCalculator(db).compute(
        provider_id="provider-openai",
        model_id="gpt-4-turbo-preview",
        started_at=datetime(2026, 7, 26, tzinfo=UTC),
        input_tokens=6,
        output_tokens=4,
        cached_input_tokens=None,
        estimated_input_tokens=None,
        estimated_output_tokens=None,
        input_usage_source="provider",
        output_usage_source="provider",
        cached_usage_source="unavailable",
    )

    assert result.cost_status == "incomplete"
    assert result.input_cost_nano_usd is None
    assert result.cached_input_cost_nano_usd is None
    assert result.output_cost_nano_usd == 8
    assert result.total_cost_nano_usd == 8
