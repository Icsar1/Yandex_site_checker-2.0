from __future__ import annotations

from app.services.allocation import (
    AllocationConfig,
    ClusterResult,
    adjusted_cpc,
    allocate_budget,
    allocate_shares,
    assign_clusters,
    build_guardrails,
    cross_minus,
    decompose_phrase,
    detect_center_of_gravity,
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


def test_phrase_cap() -> None:
    # 10 C1 phrases, phrase0 has 90× more clicks → water-fill must cap it at max_phrase_share
    # (Requires n ≥ 7 so n × cap = 10×0.15=1.5 > 1, making the cap feasible)
    from app.services.keywords import normalize_phrase as _np
    phrase_texts = [f"купить кухни вариант{i} угловые" for i in range(10)]
    keywords = [{"phrase": t, "freq": 100} for t in phrase_texts]
    forecast_idx = {
        _np(t): {"clicks": 9000.0 if i == 0 else 100.0, "avg_cpc": 50.0, "ctr": 5.0}
        for i, t in enumerate(phrase_texts)
    }
    clusters = assign_clusters(keywords, _NICHE_STEMS, _GEO, _CFG)
    allocate_shares(clusters, _CFG, forecast_idx)
    for cluster in clusters:
        for p in cluster.phrases:
            ps = p.get("phrase_share", 0.0)
            assert ps <= _CFG.max_phrase_share + 1e-6, (
                f"Phrase {p['phrase']!r} share {ps:.4f} > {_CFG.max_phrase_share}"
            )


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
        phrases=[{"phrase": "кухни", "freq": 500, "phrase_share": 0.5}],
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

    assert result["total_budget"] == 120000.0
    assert isinstance(result["clusters"], list)
    assert isinstance(result["warnings"], list)
    assert isinstance(result["top_phrases"], list)
    assert len(result["top_phrases"]) <= 10


def test_allocate_budget_e2e_total_matches() -> None:
    keywords = _rich_keywords()
    forecast: list[dict] = []
    result = allocate_budget(keywords, forecast, "кухни", set(), _CFG)
    total_budgeted = sum(c["allocated_budget"] for c in result["clusters"])
    assert abs(total_budgeted - 120000.0) < 1.0, (
        f"Total budgeted {total_budgeted} != 120000"
    )


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
