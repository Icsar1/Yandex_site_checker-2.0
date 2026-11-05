from __future__ import annotations

from app.services.allocation import (
    AllocationConfig,
    ClusterResult,
    adjusted_cpc,
    allocate_budget,
    allocate_shares,
    apply_lead_forecast,
    apply_rsya_forecast,
    assign_clusters,
    build_guardrails,
    cross_minus,
    decompose_phrase,
    detect_center_of_gravity,
    is_statistically_significant,
    validate_minus_words,
)
from app.services.keywords import extract_niche_stems

_NICHE_STEMS = extract_niche_stems("кухни")
_GEO: set[str] = set()
_CFG = AllocationConfig()


def _rich_keywords() -> list[dict]:
    return [
        {"phrase": "купить кухни угловые", "freq": 100},
        {"phrase": "купить кухни угловые белые", "freq": 80},
        {"phrase": "купить кухни угловые маленькие", "freq": 70},
        {"phrase": "купить кухни угловые большие", "freq": 90},
        {"phrase": "купить кухни угловые современные", "freq": 60},
        {"phrase": "купить кухни", "freq": 200},
        {"phrase": "заказать кухни", "freq": 180},
        {"phrase": "кухни цена", "freq": 150},
        {"phrase": "кухни стоимость", "freq": 140},
        {"phrase": "кухни калькулятор", "freq": 130},
        {"phrase": "кухни угловые", "freq": 150},
        {"phrase": "кухни белые", "freq": 120},
        {"phrase": "кухни маленькие", "freq": 110},
        {"phrase": "кухни большие", "freq": 100},
        {"phrase": "кухни деревянные", "freq": 90},
        {"phrase": "кухни", "freq": 500},
        {"phrase": "кухня", "freq": 400},
    ]


# ── 1. Декомпозиция фраз ──────────────────────────────────────────────────────

def test_decompose_c1() -> None:
    parts = decompose_phrase("купить кухни угловые", _NICHE_STEMS, _GEO)
    assert parts.cls == "C1", f"Expected C1, got {parts.cls}"
    assert parts.transactional
    assert parts.characteristic


def test_decompose_c2() -> None:
    parts = decompose_phrase("купить кухни", _NICHE_STEMS, _GEO)
    assert parts.cls == "C2", f"Expected C2, got {parts.cls}"
    assert parts.transactional
    assert not parts.characteristic


def test_decompose_c3() -> None:
    parts = decompose_phrase("кухни угловые", _NICHE_STEMS, _GEO)
    assert parts.cls == "C3", f"Expected C3, got {parts.cls}"
    assert not parts.transactional
    assert parts.characteristic


def test_decompose_c4() -> None:
    parts = decompose_phrase("кухни", _NICHE_STEMS, _GEO)
    assert parts.cls == "C4", f"Expected C4, got {parts.cls}"
    assert not parts.transactional
    assert not parts.characteristic


# ── 2. Дедуп: фраза только в самом узком кластере ────────────────────────────

def test_dedup_narrowest_only() -> None:
    keywords = _rich_keywords()
    clusters = assign_clusters(keywords, _NICHE_STEMS, _GEO, _CFG)

    by_cls: dict[str, list[str]] = {}
    for c in clusters:
        by_cls.setdefault(c.cls, []).extend(p["phrase"] for p in c.phrases)

    target = "купить кухни угловые"
    c1_phrases = by_cls.get("C1", [])
    assert target in c1_phrases, f"{target!r} not found in C1"
    assert target not in by_cls.get("C2", []), f"{target!r} found in C2 (double-count)"
    assert target not in by_cls.get("C3", []), f"{target!r} found in C3 (double-count)"
    assert target not in by_cls.get("C4", []), f"{target!r} found in C4 (double-count)"


# ── 3. Центр тяжести ─────────────────────────────────────────────────────────

def test_center_of_gravity_c1() -> None:
    p = decompose_phrase("купить кухни угловые", _NICHE_STEMS, _GEO)
    assert detect_center_of_gravity([p], "C1") is True


def test_center_of_gravity_geo() -> None:
    geo = {"москва"}
    p = decompose_phrase("кухни москва", _NICHE_STEMS, geo)
    assert detect_center_of_gravity([p], p.cls) is True


def test_center_of_gravity_c4_never() -> None:
    p = decompose_phrase("кухни", _NICHE_STEMS, _GEO)
    assert detect_center_of_gravity([p], "C4") is False


# ── 4. Веса → доли → капы ────────────────────────────────────────────────────

def test_allocation_shares_sum_to_one() -> None:
    clusters = assign_clusters(_rich_keywords(), _NICHE_STEMS, _GEO, _CFG)
    allocate_shares(clusters, _CFG, {})
    total = sum(c.allocated_share for c in clusters)
    assert abs(total - 1.0) < 1e-6, f"Shares sum to {total}, expected 1.0"


def test_broad_cap() -> None:
    # Cap is per-cluster (each C4 cluster ≤ max_broad_share), not total sum
    clusters = assign_clusters(_rich_keywords(), _NICHE_STEMS, _GEO, _CFG)
    allocate_shares(clusters, _CFG, {})
    for cluster in clusters:
        if cluster.cls == "C4":
            assert cluster.allocated_share <= _CFG.max_broad_share + 1e-6, (
                f"C4 cluster {cluster.title!r} share {cluster.allocated_share:.4f} exceeds cap"
            )


def test_phrase_rows_do_not_expose_budget_fields() -> None:
    from app.services.keywords import normalize_phrase as _np
    phrase_texts = [f"купить кухни вариант{i} угловые" for i in range(10)]
    keywords = [{"phrase": t, "freq": 100} for t in phrase_texts]
    forecast_idx = {
        _np(t): {"clicks": 9000.0 if i == 0 else 100.0, "impressions": 10000.0, "avg_cpc": 50.0, "ctr": 5.0}
        for i, t in enumerate(phrase_texts)
    }
    clusters = assign_clusters(keywords, _NICHE_STEMS, _GEO, _CFG)
    allocate_shares(clusters, _CFG, forecast_idx)

    for cluster in clusters:
        for phrase in cluster.phrases:
            assert "allocated_budget" not in phrase
            assert "phrase_share" not in phrase
            assert "spending" not in phrase


def test_center_gets_largest_share() -> None:
    clusters = assign_clusters(_rich_keywords(), _NICHE_STEMS, _GEO, _CFG)
    allocate_shares(clusters, _CFG, {})
    cog = [c for c in clusters if c.is_center_of_gravity]
    general = [c for c in clusters if c.type == "general"]
    if cog and general:
        max_cog = max(c.allocated_share for c in cog)
        max_broad = max(c.allocated_share for c in general)
        assert max_cog > max_broad, (
            f"Center of gravity share {max_cog} not greater than broad share {max_broad}"
        )


# ── 5. BROAD_BID_FACTOR ───────────────────────────────────────────────────────

def test_broad_bid_factor_c4() -> None:
    cfg = AllocationConfig(broad_bid_factor=0.5)
    assert adjusted_cpc("C4", 100.0, cfg) == 50.0


def test_broad_bid_factor_non_c4() -> None:
    cfg = AllocationConfig(broad_bid_factor=0.5)
    assert adjusted_cpc("C1", 100.0, cfg) == 100.0
    assert adjusted_cpc("C2", 80.0, cfg) == 80.0
    assert adjusted_cpc("C3", 60.0, cfg) == 60.0


# ── 6. Минимальные критерии ───────────────────────────────────────────────────

def test_min_criteria_merge() -> None:
    cfg = AllocationConfig(min_cluster_freq=50, min_cluster_keys=5)
    # C1 bucket: только 2 фразы + freq < min_cluster_keys=5 → слияние
    keywords = [
        {"phrase": "купить кухни угловые", "freq": 30},
        {"phrase": "купить кухни белые", "freq": 25},
        {"phrase": "кухни", "freq": 300},
        {"phrase": "кухня", "freq": 250},
        {"phrase": "кухонный", "freq": 200},
        {"phrase": "кухонные", "freq": 180},
        {"phrase": "кухонная", "freq": 160},
    ]
    clusters = assign_clusters(keywords, _NICHE_STEMS, _GEO, cfg)
    c1_clusters = [c for c in clusters if c.cls == "C1"]
    for c in c1_clusters:
        assert c.n_keys >= cfg.min_cluster_keys or c.total_freq >= cfg.min_cluster_freq, (
            f"C1 cluster survived merge with n_keys={c.n_keys}, total_freq={c.total_freq}"
        )


def test_low_freq_bucket() -> None:
    keywords = [
        {"phrase": "купить кухни", "freq": 5},
        {"phrase": "кухни цена", "freq": 15},
        {"phrase": "кухни", "freq": 200},
    ]
    clusters = assign_clusters(keywords, _NICHE_STEMS, _GEO, _CFG)
    low_freq_cluster = next((c for c in clusters if c.base == "малопоказы"), None)
    assert low_freq_cluster is not None, "Bucket 'малопоказы' not found"
    low_phrases = {p["phrase"] for p in low_freq_cluster.phrases}
    assert "купить кухни" in low_phrases
    assert "кухни цена" in low_phrases


# ── 7. Кросс-минусовка ───────────────────────────────────────────────────────

def test_cross_minus_basic() -> None:
    child = [decompose_phrase("купить кухни угловые", _NICHE_STEMS, _GEO)]
    parent = [decompose_phrase("кухни", _NICHE_STEMS, _GEO)]
    minus = cross_minus(child, parent)
    # "купить" (транзакц.) и "угловые" (хар-ка) — уникальны для child
    assert len(minus) >= 1, f"Expected cross-minus tokens, got: {minus}"
    assert any(m in minus for m in ("купить", "угловые")), f"Got: {minus}"


def test_cross_minus_full_coverage() -> None:
    child = [
        decompose_phrase("купить кухни угловые", _NICHE_STEMS, _GEO),
        decompose_phrase("заказать кухни белые", _NICHE_STEMS, _GEO),
    ]
    parent = [decompose_phrase("кухни", _NICHE_STEMS, _GEO)]
    minus = cross_minus(child, parent)
    assert len(minus) >= 2, f"Expected ≥2 minus words, got {minus}"


# ── 8. Гардрейлы ─────────────────────────────────────────────────────────────

def test_guardrails_warning_when_broad_dominates() -> None:
    cluster = ClusterResult(
        base="кухни", title="кухни / general",
        type="general", cls="C4",
        is_center_of_gravity=False,
        n_keys=1, total_freq=500,
        allocated_share=0.5,
        allocated_budget=60000.0,
        phrases=[{"phrase": "кухни", "freq": 500}],
    )
    warnings = build_guardrails([cluster], _CFG)
    assert any("голый базис" in w for w in warnings), f"No guardrail warning: {warnings}"


def test_guardrails_no_false_positive() -> None:
    clusters = assign_clusters(_rich_keywords(), _NICHE_STEMS, _GEO, _CFG)
    allocate_shares(clusters, _CFG, {})
    broad_total = sum(c.allocated_share for c in clusters if c.type == "general")
    warnings = build_guardrails(clusters, _CFG)
    if broad_total <= _CFG.max_broad_share:
        broad_warnings = [w for w in warnings if "голый базис" in w]
        assert not broad_warnings, f"False positive guardrail: {broad_warnings}"


# ── 9. E2E оркестратор ───────────────────────────────────────────────────────

def test_allocate_budget_e2e_structure() -> None:
    keywords = _rich_keywords()
    forecast = [
        {"phrase": "купить кухни угловые", "impressions": 1000, "clicks": 50, "avg_cpc": 80.0, "ctr": 5.0},
        {"phrase": "кухни", "impressions": 50000, "clicks": 500, "avg_cpc": 20.0, "ctr": 1.0},
    ]
    result = allocate_budget(keywords, forecast, "кухни", set(), _CFG)

    assert result["methodology_version"] == 3
    assert result["total_budget"] == 2000.0
    assert len(result["budget_scenarios"]) == 4
    assert result["clean_cpc"]["value"] == 20.0
    assert result["budget_scenarios"][1]["id"] == "recommended"
    assert result["budget_scenarios"][1]["budget"] == 2000.0
    assert isinstance(result["clusters"], list)
    assert isinstance(result["warnings"], list)
    assert isinstance(result["top_phrases"], list)
    assert len(result["top_phrases"]) <= 10


def test_allocate_budget_e2e_total_matches() -> None:
    keywords = _rich_keywords()
    forecast: list[dict] = []
    result = allocate_budget(keywords, forecast, "кухни", set(), _CFG)
    total_budgeted = sum(c["allocated_budget"] for c in result["clusters"])
    assert total_budgeted == 0.0
    assert result["total_budget"] == 0.0


def test_allocate_budget_broad_never_exceeds_cap() -> None:
    # Each individual C4/general cluster must not exceed max_broad_share (cap is per-cluster)
    keywords = _rich_keywords()
    forecast: list[dict] = []
    result = allocate_budget(keywords, forecast, "кухни", set(), _CFG)
    for cluster in result["clusters"]:
        if cluster["cls"] == "C4":
            assert cluster["allocated_share"] <= _CFG.max_broad_share + 1e-6, (
                f"C4 cluster {cluster['title']!r} share {cluster['allocated_share']:.4f} "
                f"exceeds cap {_CFG.max_broad_share}"
            )


def test_cross_minus_protects_commercial_core_words() -> None:
    child = [decompose_phrase("ремонт кухни цена", extract_niche_stems("ремонт кухни"), set())]
    parent = [decompose_phrase("ремонт кухни", extract_niche_stems("ремонт кухни"), set())]

    minus = cross_minus(child, parent)

    assert "цена" not in minus


def test_recommended_budget_is_clicks_times_clean_cpc() -> None:
    keywords = [
        {"phrase": "ремонт квартир цена", "freq": 100, "score": 1.0, "priority": "high"},
    ]
    forecast = [
        {"phrase": "ремонт квартир цена", "impressions": 100, "clicks": 10, "spending": 2000, "avg_cpc": 200, "ctr": 10.0},
    ]

    result = allocate_budget(keywords, forecast, "ремонт квартир", set(), _CFG)

    # No artificial minimum-budget floor: budget = target_clicks * clean_cpc.
    assert result["recommended_budget"] == 100 * 200.0
    assert result["budget_scenarios"][0]["budget"] == 50 * 200.0
    assert result["budget_scenarios"][1]["budget"] == 100 * 200.0


def test_is_statistically_significant_threshold() -> None:
    assert is_statistically_significant(30, 1000) is True
    assert is_statistically_significant(29, 1000) is False
    assert is_statistically_significant(2, 2) is False  # 2 clicks -> "100% CTR" noise


def test_low_click_phrase_ctr_flagged_as_not_significant() -> None:
    # Regression: top-10 table must not present a 100% CTR computed from 2 clicks
    # as a reliable figure.
    keywords = [{"phrase": "купить кухни угловые", "freq": 100}]
    forecast = [
        {"phrase": "купить кухни угловые", "impressions": 2, "clicks": 2, "avg_cpc": 80.0, "ctr": 100.0},
    ]

    result = allocate_budget(keywords, forecast, "кухни", set(), _CFG)
    phrase = next(p for p in result["top_phrases"] if p["phrase"] == "купить кухни угловые")

    assert phrase["ctr_significant"] is False


def test_scenario_budget_exceeding_demand_is_not_reported_as_100_percent() -> None:
    # Regression for the "стартовый бюджет покрывает 100% спроса" bug: when the
    # click-based scenario budget vastly exceeds the collected phrase
    # demand (2k), the scenario must NOT silently report 100% coverage.
    keywords = [
        {"phrase": "ремонт квартир цена", "freq": 100, "score": 1.0, "priority": "high"},
    ]
    forecast = [
        {"phrase": "ремонт квартир цена", "impressions": 100, "clicks": 10, "spending": 2000, "avg_cpc": 200, "ctr": 10.0},
    ]

    result = allocate_budget(keywords, forecast, "ремонт квартир", set(), _CFG)
    recommended = result["budget_scenarios"][1]

    assert recommended["id"] == "recommended"
    assert recommended["budget"] == 100 * 200.0
    assert recommended["demand_full_rub"] == result["full_demand"]["budget_max"]
    assert recommended["exceeds_demand"] is True
    assert recommended["exceeds_demand_ratio"] >= 3.0
    # pct_of_demand must reflect the real (large) overshoot, never clipped to 100
    assert recommended["pct_of_demand"] > 100.0
    assert any(
        "минимально жизнеспособном уровне" in warning
        and "спроса" in warning
        for warning in result["warnings"]
    )


def test_scenario_budget_range_uses_forecast_error_margin() -> None:
    keywords = [
        {"phrase": "ремонт квартир цена", "freq": 100, "score": 1.0, "priority": "high"},
    ]
    forecast = [
        {"phrase": "ремонт квартир цена", "impressions": 1000, "clicks": 100, "spending": 20000, "avg_cpc": 200, "ctr": 10.0},
    ]
    cfg = AllocationConfig(forecast_error_margin=0.3)

    result = allocate_budget(keywords, forecast, "ремонт квартир", set(), cfg)

    assert result["forecast_error_margin"] == 0.3
    assert result["full_demand"]["forecast_error_margin"] == 0.3
    recommended = next(s for s in result["budget_scenarios"] if s["id"] == "recommended")
    budget = recommended["budget"]
    assert recommended["budget_low"] == round(budget * 0.7, 2)
    assert recommended["budget_high"] == round(budget * 1.3, 2)


def test_validate_minus_words_flags_conflict_with_active_phrase() -> None:
    # Regression for the "минус-слово 'губ' при наличии фразы 'коррекция губ'" bug:
    # a minus word must never be auto-applied if it would suppress another
    # cluster's own active phrase.
    clean, review = validate_minus_words(["губ", "цена"], ["коррекция губ отзывы"])
    assert clean == ["цена"]
    assert review == ["губ"]


def test_validate_minus_words_no_conflict_passes_through() -> None:
    clean, review = validate_minus_words(["акция"], ["коррекция губ отзывы"])
    assert clean == ["акция"]
    assert review == []


def test_cluster_minus_words_conflicting_with_sibling_go_to_review() -> None:
    # End-to-end reproduction of the TZ example: "увеличение губ" and "коррекция
    # губ" fall into different clusters (neither matches the broad niche stems),
    # so a naive cross-minus would suppress "губ" for one cluster while the other
    # cluster still actively targets a phrase containing "губ".
    niche = "интимная пластика"
    keywords = [
        {"phrase": "увеличение губ цена", "freq": 100, "priority": "high"},
        {"phrase": "коррекция губ отзывы", "freq": 100, "priority": "medium"},
    ]
    forecast = [
        {"phrase": "увеличение губ цена", "impressions": 1000, "clicks": 100, "spending": 20000, "avg_cpc": 200, "ctr": 10.0},
        {"phrase": "коррекция губ отзывы", "impressions": 1000, "clicks": 100, "spending": 20000, "avg_cpc": 200, "ctr": 10.0},
    ]

    result = allocate_budget(keywords, forecast, niche, set(), AllocationConfig())

    for cluster in result["clusters"]:
        assert "губ" not in cluster["minus_words"], (
            f"'губ' leaked into minus_words for {cluster['title']!r}, "
            "would suppress a sibling cluster's active phrase"
        )
        assert "губ" in cluster["minus_words_review"]


def test_cluster_title_is_human_readable_not_internal_id() -> None:
    # Regression: clusters whose phrases don't match the niche basis used to be
    # titled with the raw internal identifier, e.g. "__nb_C3 / characteristic".
    niche = "интимная пластика"
    keywords = [{"phrase": "коррекция губ отзывы", "freq": 100, "priority": "medium"}]

    result = allocate_budget(keywords, [], niche, set(), AllocationConfig())

    for cluster in result["clusters"]:
        assert not cluster["title"].startswith("__nb_"), cluster["title"]
        assert "/" not in cluster["title"]


def test_allocate_budget_intent_breakdown_reflects_demand_shares() -> None:
    keywords = [
        {"phrase": "интимная пластика цена", "freq": 100, "priority": "high"},
        {"phrase": "симптомы опущения матки", "freq": 100, "priority": "medium"},
    ]
    forecast = [
        {"phrase": "интимная пластика цена", "impressions": 1000, "clicks": 50, "spending": 30000, "avg_cpc": 200, "ctr": 5.0},
        {"phrase": "симптомы опущения матки", "impressions": 1000, "clicks": 50, "spending": 10000, "avg_cpc": 200, "ctr": 5.0},
    ]

    result = allocate_budget(keywords, forecast, "интимная пластика", set(), AllocationConfig())

    breakdown = result["intent_breakdown"]
    assert breakdown["commercial"]["demand_rub"] == 30000.0
    assert breakdown["informational"]["demand_rub"] == 10000.0
    assert breakdown["informational"]["share"] == 0.25


def test_allocate_budget_warns_when_informational_share_exceeds_threshold() -> None:
    keywords = [
        {"phrase": "интимная пластика цена", "freq": 100, "priority": "high"},
        {"phrase": "симптомы опущения матки", "freq": 100, "priority": "medium"},
    ]
    forecast = [
        {"phrase": "интимная пластика цена", "impressions": 1000, "clicks": 50, "spending": 10000, "avg_cpc": 200, "ctr": 5.0},
        {"phrase": "симптомы опущения матки", "impressions": 1000, "clicks": 50, "spending": 20000, "avg_cpc": 200, "ctr": 5.0},
    ]
    cfg = AllocationConfig(informational_share_warn_threshold=0.30)

    result = allocate_budget(keywords, forecast, "интимная пластика", set(), cfg)

    assert any("информационных запросов" in w for w in result["warnings"])


def test_allocate_budget_excludes_informational_phrases_when_configured() -> None:
    keywords = [
        {"phrase": "интимная пластика цена", "freq": 100, "priority": "high"},
        {"phrase": "симптомы опущения матки", "freq": 100, "priority": "medium"},
    ]
    forecast = [
        {"phrase": "интимная пластика цена", "impressions": 1000, "clicks": 50, "spending": 10000, "avg_cpc": 200, "ctr": 5.0},
        {"phrase": "симптомы опущения матки", "impressions": 1000, "clicks": 50, "spending": 20000, "avg_cpc": 200, "ctr": 5.0},
    ]
    cfg = AllocationConfig(exclude_informational_phrases=True)

    result = allocate_budget(keywords, forecast, "интимная пластика", set(), cfg)

    phrases_in_clusters = {p["phrase"] for c in result["clusters"] for p in c["phrases"]}
    assert "симптомы опущения матки" not in phrases_in_clusters
    assert "интимная пластика цена" in phrases_in_clusters


def test_scenario_budget_range_zero_margin_collapses_to_point_estimate() -> None:
    keywords = [
        {"phrase": "ремонт квартир цена", "freq": 100, "score": 1.0, "priority": "high"},
    ]
    forecast = [
        {"phrase": "ремонт квартир цена", "impressions": 1000, "clicks": 100, "spending": 20000, "avg_cpc": 200, "ctr": 10.0},
    ]
    cfg = AllocationConfig(forecast_error_margin=0.0)

    result = allocate_budget(keywords, forecast, "ремонт квартир", set(), cfg)
    recommended = next(s for s in result["budget_scenarios"] if s["id"] == "recommended")

    assert recommended["budget_low"] == recommended["budget"]
    assert recommended["budget_high"] == recommended["budget"]


def test_apply_lead_forecast_with_explicit_conversion_rate() -> None:
    scenarios = [{"id": "recommended", "budget": 10000.0, "clicks": 100.0}]

    result = apply_lead_forecast(scenarios, expected_conversion_rate=0.05)

    assert result[0]["cr_is_estimated"] is False
    assert result[0]["leads"] == 5.0
    assert result[0]["cpl"] == 2000.0


def test_apply_lead_forecast_without_conversion_rate_uses_benchmark_range() -> None:
    scenarios = [{"id": "recommended", "budget": 10000.0, "clicks": 100.0}]

    result = apply_lead_forecast(
        scenarios, expected_conversion_rate=None, cr_benchmark_low=0.02, cr_benchmark_high=0.05
    )

    assert result[0]["cr_is_estimated"] is True
    assert result[0]["leads_low"] == 2.0
    assert result[0]["leads_high"] == 5.0
    assert result[0]["cpl_low"] == 2000.0
    assert result[0]["cpl_high"] == 5000.0
    assert "leads" not in result[0]


def test_apply_lead_forecast_zero_clicks_gives_none_cpl() -> None:
    scenarios = [{"id": "cautious", "budget": 0.0, "clicks": 0.0}]

    result = apply_lead_forecast(scenarios, expected_conversion_rate=0.05)

    assert result[0]["leads"] == 0.0
    assert result[0]["cpl"] is None


def test_allocate_budget_wires_lead_forecast_into_scenarios() -> None:
    keywords = [
        {"phrase": "ремонт квартир цена", "freq": 100, "score": 1.0, "priority": "high"},
    ]
    forecast = [
        {"phrase": "ремонт квартир цена", "impressions": 1000, "clicks": 100, "spending": 20000, "avg_cpc": 200, "ctr": 10.0},
    ]
    cfg = AllocationConfig(expected_conversion_rate=0.1)

    result = allocate_budget(keywords, forecast, "ремонт квартир", set(), cfg)
    recommended = next(s for s in result["budget_scenarios"] if s["id"] == "recommended")

    assert recommended["cr_is_estimated"] is False
    assert recommended["leads"] == recommended["clicks"] * 0.1


def test_allocate_budget_produces_multiple_clusters_with_distinct_priority_and_share() -> None:
    keywords = [
        {"phrase": "увеличение губ цена", "freq": 500, "score": 1.0, "priority": "high"},
        {"phrase": "увеличение губ купить", "freq": 300, "score": 0.9, "priority": "high"},
        {"phrase": "коррекция губ отзывы", "freq": 200, "score": 0.8, "priority": "medium"},
    ]
    forecast = [
        {"phrase": kw["phrase"], "impressions": 1000, "clicks": 50, "spending": 5000, "avg_cpc": 100, "ctr": 5.0}
        for kw in keywords
    ]

    result = allocate_budget(keywords, forecast, "интимная пластика", set(), AllocationConfig())
    clusters = result["clusters"]

    assert len(clusters) > 1
    priorities = {c["priority"] for c in clusters}
    shares = {c["allocated_share"] for c in clusters}
    assert len(priorities) > 1 or len(shares) > 1
    assert all(c["title"] != "" for c in clusters)


def test_apply_rsya_forecast_derives_cpm_and_reach_from_search_cpc() -> None:
    scenarios = [{"id": "recommended", "title": "Рекомендуемый", "budget": 10000.0}]

    result = apply_rsya_forecast(
        scenarios, search_clean_cpc=100.0, rsya_cpc_factor=0.4, rsya_ctr_pct=0.2
    )

    rsya_cpc = 100.0 * 0.4
    expected_cpm = rsya_cpc * 0.2 * 10
    assert result[0]["cpc"] == round(rsya_cpc, 2)
    assert result[0]["cpm"] == round(expected_cpm, 2)
    assert result[0]["clicks"] == round(10000.0 / rsya_cpc)
    assert result[0]["reach"] > result[0]["clicks"]


def test_apply_rsya_forecast_zero_cpc_gives_zero_metrics() -> None:
    scenarios = [{"id": "recommended", "title": "Рекомендуемый", "budget": 10000.0}]

    result = apply_rsya_forecast(scenarios, search_clean_cpc=0.0)

    assert result[0]["cpm"] == 0.0
    assert result[0]["clicks"] == 0
    assert result[0]["reach"] == 0


def test_allocate_budget_default_campaign_type_has_no_rsya_forecast() -> None:
    keywords = [{"phrase": "ремонт квартир цена", "freq": 100, "score": 1.0, "priority": "high"}]
    forecast = [
        {"phrase": "ремонт квартир цена", "impressions": 1000, "clicks": 100, "spending": 20000, "avg_cpc": 200, "ctr": 10.0},
    ]

    result = allocate_budget(keywords, forecast, "ремонт квартир", set(), AllocationConfig())

    assert result["campaign_type"] == "search"
    assert result["rsya_forecast"] == []


def test_allocate_budget_both_campaign_type_produces_rsya_forecast() -> None:
    keywords = [{"phrase": "ремонт квартир цена", "freq": 100, "score": 1.0, "priority": "high"}]
    forecast = [
        {"phrase": "ремонт квартир цена", "impressions": 1000, "clicks": 100, "spending": 20000, "avg_cpc": 200, "ctr": 10.0},
    ]
    cfg = AllocationConfig(campaign_type="both")

    result = allocate_budget(keywords, forecast, "ремонт квартир", set(), cfg)

    assert result["rsya_forecast"]
    assert all("cpm" in item and "reach" in item for item in result["rsya_forecast"])
