from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.keywords import (
    COMMERCIAL_MARKERS,
    _RU_STOPWORDS,
    _marker_matches,
    classify_intent_category,
    extract_niche_stems,
    normalize_phrase,
)

_GEO_MARKERS = {
    "рядом", "адрес", "метро", "район", "улица", "город",
    "москва", "спб", "питер", "краснодар", "екатеринбург", "новосибирск", "казань",
}

PhraseClass = Literal["C1", "C2", "C3", "C4"]
ClusterType = Literal["transactional", "characteristic", "general"]

METHODOLOGY_VERSION = 3
FORECAST_KEYWORD_LIMIT = 100

_SAFE_MINUS_BLOCKLIST = {
    "купить",
    "заказать",
    "цена",
    "стоимость",
    "прайс",
    "расчет",
    "рассчитать",
    "калькулятор",
    "смета",
    "под",
    "ключ",
    "москва",
    "спб",
    "питер",
}

_SCENARIO_DEFS = (
    {
        "id": "cautious",
        "title": "Осторожный старт",
        "target_clicks": 50,
        "priorities": {"high"},
    },
    {
        "id": "recommended",
        "title": "Рекомендуемый старт",
        "target_clicks": 100,
        "priorities": {"high", "medium"},
    },
    {
        "id": "confident",
        "title": "Уверенный запуск",
        "target_clicks": 150,
        "priorities": {"high", "medium", "low"},
    },
    {
        "id": "full",
        "title": "Полный спрос",
        "target_clicks": None,
        "priorities": {"high", "medium", "low"},
    },
)


@dataclass(frozen=True)
class PhraseParts:
    phrase: str
    basis: frozenset[str]
    transactional: frozenset[str]
    characteristic: frozenset[str]
    geo: frozenset[str]
    cls: PhraseClass


@dataclass
class ClusterResult:
    base: str
    title: str
    type: ClusterType
    cls: PhraseClass
    is_center_of_gravity: bool
    n_keys: int
    total_freq: int
    allocated_share: float = 0.0
    allocated_budget: float = 0.0
    minus_words: list[str] = field(default_factory=list)
    minus_words_review: list[str] = field(default_factory=list)
    phrases: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class AllocationConfig:
    total_budget: float = 120000.0
    weight_center: float = 1.0
    weight_transactional: float = 0.7
    weight_characteristic: float = 0.4
    weight_broad: float = 0.15
    max_broad_share: float = 0.10
    broad_bid_factor: float = 0.5
    min_cluster_freq: int = 50
    min_cluster_keys: int = 5
    low_freq_threshold: int = 20
    forecast_error_margin: float = 0.3
    informational_share_warn_threshold: float = 0.30
    exclude_informational_phrases: bool = False
    expected_conversion_rate: float | None = None
    cr_benchmark_low: float = 0.02
    cr_benchmark_high: float = 0.05
    campaign_type: str = "search"
    rsya_cpc_factor: float = 0.4
    rsya_ctr_pct: float = 0.15

    @classmethod
    def from_settings(cls, settings: object) -> "AllocationConfig":
        raw_cr = getattr(settings, "EXPECTED_CONVERSION_RATE", None)
        return cls(
            total_budget=float(getattr(settings, "MEDIA_PLAN_BUDGET", 120000)),
            weight_center=float(getattr(settings, "ALLOC_WEIGHT_CENTER", 1.0)),
            weight_transactional=float(getattr(settings, "ALLOC_WEIGHT_TRANSACTIONAL", 0.7)),
            weight_characteristic=float(getattr(settings, "ALLOC_WEIGHT_CHARACTERISTIC", 0.4)),
            weight_broad=float(getattr(settings, "ALLOC_WEIGHT_BROAD", 0.15)),
            max_broad_share=float(getattr(settings, "ALLOC_MAX_BROAD_SHARE", 0.10)),
            broad_bid_factor=float(getattr(settings, "ALLOC_BROAD_BID_FACTOR", 0.5)),
            min_cluster_freq=int(getattr(settings, "ALLOC_MIN_CLUSTER_FREQ", 50)),
            min_cluster_keys=int(getattr(settings, "ALLOC_MIN_CLUSTER_KEYS", 5)),
            low_freq_threshold=int(getattr(settings, "ALLOC_LOW_FREQ_THRESHOLD", 20)),
            forecast_error_margin=float(getattr(settings, "FORECAST_ERROR_MARGIN", 0.3)),
            informational_share_warn_threshold=float(
                getattr(settings, "INFORMATIONAL_SHARE_WARN_THRESHOLD", 0.30)
            ),
            exclude_informational_phrases=bool(
                getattr(settings, "EXCLUDE_INFORMATIONAL_PHRASES", False)
            ),
            expected_conversion_rate=float(raw_cr) if raw_cr is not None else None,
            cr_benchmark_low=float(getattr(settings, "CR_BENCHMARK_LOW", 0.02)),
            cr_benchmark_high=float(getattr(settings, "CR_BENCHMARK_HIGH", 0.05)),
            campaign_type=str(getattr(settings, "CAMPAIGN_TYPE", "search")),
            rsya_cpc_factor=float(getattr(settings, "RSYA_CPC_FACTOR", 0.4)),
            rsya_ctr_pct=float(getattr(settings, "RSYA_CTR_PCT", 0.15)),
        )


def decompose_phrase(
    phrase: str,
    niche_stems: set[str],
    geo_tokens: set[str],
) -> PhraseParts:
    norm = normalize_phrase(phrase)
    tokens = norm.split()
    token_set = set(tokens)

    basis = frozenset(
        tok for tok in tokens
        if niche_stems and any(tok.startswith(stem) for stem in niche_stems)
    )

    matching_markers: set[str] = set()
    trans_tokens: set[str] = set()
    for marker in COMMERCIAL_MARKERS:
        if _marker_matches(norm, token_set, marker):
            matching_markers.add(marker)
            norm_marker = normalize_phrase(marker)
            trans_tokens.update(norm_marker.split())

    geo = frozenset(tok for tok in tokens if tok in _GEO_MARKERS or tok in geo_tokens)

    characteristic = frozenset(
        tok for tok in tokens
        if tok not in basis
        and tok not in trans_tokens
        and tok not in geo
        and tok not in _RU_STOPWORDS
        and len(tok) >= 2
    )

    has_trans = bool(matching_markers) or bool(geo)
    has_char = bool(characteristic)
    if has_trans and has_char:
        cls: PhraseClass = "C1"
    elif has_trans:
        cls = "C2"
    elif has_char:
        cls = "C3"
    else:
        cls = "C4"

    return PhraseParts(
        phrase=norm,
        basis=basis,
        transactional=frozenset(matching_markers),
        characteristic=characteristic,
        geo=geo,
        cls=cls,
    )


def detect_center_of_gravity(parts_list: list[PhraseParts], cls: PhraseClass) -> bool:
    if cls == "C4":
        return False
    if cls == "C1":
        return True
    return any(p.geo for p in parts_list)


def _cluster_weight(is_cog: bool, cls: PhraseClass, cfg: AllocationConfig) -> float:
    if is_cog:
        return cfg.weight_center
    if cls == "C2":
        return cfg.weight_transactional
    if cls == "C3":
        return cfg.weight_characteristic
    return cfg.weight_broad


def _water_fill_cap(
    shares: dict[int, float], cap: float, broad_keys: set[int]
) -> dict[int, float]:
    # Iteratively cap broad cluster shares and redistribute excess onto uncapped clusters
    result = dict(shares)
    for _ in range(20):
        over = {k for k in broad_keys if result.get(k, 0.0) > cap + 1e-12}
        if not over:
            break
        excess = sum(result[k] - cap for k in over)
        for k in over:
            result[k] = cap
        uncapped = [k for k in result if k not in broad_keys]
        uncapped_total = sum(result[k] for k in uncapped)
        if uncapped_total > 0:
            factor = (uncapped_total + excess) / uncapped_total
            for k in uncapped:
                result[k] *= factor
        elif uncapped:
            per = excess / len(uncapped)
            for k in uncapped:
                result[k] = result.get(k, 0.0) + per
    return result


def _water_fill_phrase_cap(
    shares: dict[int, float], cap: float
) -> dict[int, float]:
    # Iteratively cap per-phrase shares within a cluster and redistribute excess
    result = dict(shares)
    for _ in range(20):
        over = {k: v for k, v in result.items() if v > cap + 1e-12}
        if not over:
            break
        under = {k: v for k, v in result.items() if v <= cap}
        if not under:
            # All phrases hit the cap — equal distribution is unavoidable, keep as-is
            break
        excess = sum(v - cap for v in over.values())
        for k in over:
            result[k] = cap
        under_total = sum(under.values())
        if under_total > 0:
            factor = (under_total + excess) / under_total
            for k in under:
                result[k] *= factor
    return result


def cross_minus(
    child_parts: list[PhraseParts],
    parent_parts: list[PhraseParts],
) -> list[str]:
    child_tokens: set[str] = set()
    protected: set[str] = set(_SAFE_MINUS_BLOCKLIST)
    for p in child_parts:
        child_tokens.update(p.transactional)
        child_tokens.update(p.characteristic)
        protected.update(p.basis)
        protected.update(p.geo)
    parent_tokens: set[str] = set()
    for p in parent_parts:
        parent_tokens.update(p.transactional)
        parent_tokens.update(p.characteristic)
        protected.update(p.basis)
        protected.update(p.geo)
    return sorted(token for token in (child_tokens - parent_tokens) if token not in protected)


def validate_minus_words(
    minus_words: list[str], active_phrases: list[str]
) -> tuple[list[str], list[str]]:
    """Split minus words into (safe, needs_review): a minus word that is itself a
    token of one of the given active phrases (e.g. a sibling cluster's keywords)
    would silently cut off that phrase's traffic, so it must not be auto-applied."""
    active_tokens: set[str] = set()
    for phrase in active_phrases:
        active_tokens.update(normalize_phrase(phrase).split())
    clean: list[str] = []
    needs_review: list[str] = []
    for word in minus_words:
        if word in active_tokens:
            needs_review.append(word)
        else:
            clean.append(word)
    return clean, needs_review


def _readable_cluster_title(
    basis_key: str, cluster_type: ClusterType, items: list[tuple[dict, "PhraseParts"]]
) -> str:
    if not basis_key.startswith("__nb_"):
        return " ".join(tok.capitalize() for tok in basis_key.split())
    counter: Counter[str] = Counter()
    for kw, parts in items:
        weight = int(kw.get("freq") or 0) or 1
        for tok in set(parts.transactional) | set(parts.characteristic):
            counter[tok] += weight
    top_words = [w for w, _ in counter.most_common(2)]
    if top_words:
        return " ".join(w.capitalize() for w in top_words)
    return "Общие фразы" if cluster_type == "general" else "Разное"


def build_guardrails(clusters: list[ClusterResult], cfg: AllocationConfig) -> list[str]:
    warnings: list[str] = []
    broad_total = sum(c.allocated_share for c in clusters if c.type == "general")
    if broad_total > cfg.max_broad_share + 1e-9:
        warnings.append(
            f"⚠ Центр тяжести смещён на голый базис (общие фразы получают "
            f"{broad_total:.0%}), нужно углубление семантики"
        )
    return warnings


def assign_clusters(
    keywords: list[dict],
    niche_stems: set[str],
    geo_tokens: set[str],
    cfg: AllocationConfig,
) -> list[ClusterResult]:
    low_freq_items: list[tuple[dict, PhraseParts]] = []
    family_map: dict[str, dict[str, list[tuple[dict, PhraseParts]]]] = {}

    for kw in keywords:
        phrase = str(kw.get("phrase") or "")
        freq = int(kw.get("freq") or 0)
        if not phrase:
            continue

        parts = decompose_phrase(phrase, niche_stems, geo_tokens)

        if freq < cfg.low_freq_threshold:
            low_freq_items.append((kw, parts))
            continue

        basis_key = " ".join(sorted(parts.basis)) if parts.basis else f"__nb_{parts.cls}"
        family_map.setdefault(basis_key, {})
        family_map[basis_key].setdefault(parts.cls, [])
        family_map[basis_key][parts.cls].append((kw, parts))

    results: list[ClusterResult] = []

    for basis_key, buckets in family_map.items():
        # Merge underpopulated buckets into parent class (C1→C2, C2→C4, C3→C4)
        changed = True
        while changed:
            changed = False
            for cls_check in ("C1", "C2", "C3"):
                if cls_check not in buckets:
                    continue
                items = buckets[cls_check]
                total_freq = sum(int(kw.get("freq") or 0) for kw, _ in items)
                if total_freq < cfg.min_cluster_freq and len(items) < cfg.min_cluster_keys:
                    parent_cls = {"C1": "C2", "C2": "C4", "C3": "C4"}[cls_check]
                    buckets.setdefault(parent_cls, [])
                    buckets[parent_cls].extend(items)
                    del buckets[cls_check]
                    changed = True
                    break

        for cls, items in buckets.items():
            parts_list = [p for _, p in items]
            is_cog = detect_center_of_gravity(parts_list, cls)
            cluster_type: ClusterType = (
                "transactional" if cls in ("C1", "C2")
                else "characteristic" if cls == "C3"
                else "general"
            )
            total_freq = sum(int(kw.get("freq") or 0) for kw, _ in items)
            phrases_data = [
                {"phrase": p.phrase, "freq": int(kw.get("freq") or 0)}
                for kw, p in items
            ]
            results.append(
                ClusterResult(
                    base=basis_key,
                    title=_readable_cluster_title(basis_key, cluster_type, items),
                    type=cluster_type,
                    cls=cls,
                    is_center_of_gravity=is_cog,
                    n_keys=len(items),
                    total_freq=total_freq,
                    phrases=phrases_data,
                )
            )

    if low_freq_items:
        total_freq = sum(int(kw.get("freq") or 0) for kw, _ in low_freq_items)
        results.append(
            ClusterResult(
                base="малопоказы",
                title="Низкочастотные фразы",
                type="general",
                cls="C4",
                is_center_of_gravity=False,
                n_keys=len(low_freq_items),
                total_freq=total_freq,
                phrases=[
                    {"phrase": p.phrase, "freq": int(kw.get("freq") or 0)}
                    for kw, p in low_freq_items
                ],
            )
        )

    return results


def _compute_intent_breakdown(forecast_rows: list[dict]) -> dict[str, dict]:
    demand_by_category = {"commercial": 0.0, "informational": 0.0, "mixed": 0.0}
    impressions_by_category = {"commercial": 0.0, "informational": 0.0, "mixed": 0.0}
    for row in forecast_rows:
        category = classify_intent_category(str(row.get("phrase") or ""))
        demand_by_category[category] += _to_float(row.get("spending"))
        impressions_by_category[category] += _to_float(row.get("impressions"))
    total_demand = sum(demand_by_category.values())
    return {
        category: {
            "demand_rub": round(demand, 2),
            "share": round(demand / total_demand, 4) if total_demand > 0 else 0.0,
            "impressions": round(impressions_by_category[category], 0),
        }
        for category, demand in demand_by_category.items()
    }


def is_statistically_significant(
    clicks: int | float, impressions: int | float, threshold: int = 30
) -> bool:
    """A CTR/conversion rate computed from fewer than `threshold` clicks is noise,
    not a stable estimate (e.g. 1 click of 2 impressions = "50% CTR")."""
    return float(clicks or 0) >= threshold


def adjusted_cpc(cls: PhraseClass, cpc: float, cfg: AllocationConfig) -> float:
    if cls == "C4":
        return cpc * cfg.broad_bid_factor
    return cpc


def _compute_phrase_metrics(
    phrase_budget: float, adj_cpc: float, ctr: float
) -> tuple[float, float]:
    clicks = phrase_budget / adj_cpc if adj_cpc > 0 else 0.0
    impressions = clicks / (ctr / 100.0) if ctr > 0 else 0.0
    return clicks, impressions


def allocate_shares(
    clusters: list[ClusterResult],
    cfg: AllocationConfig,
    forecast_index: dict[str, dict] | None = None,
) -> None:
    if not clusters:
        return
    forecast_index = forecast_index or {}

    weights = {
        i: _cluster_weight(c.is_center_of_gravity, c.cls, cfg)
        for i, c in enumerate(clusters)
    }
    total_w = sum(weights.values()) or 1.0
    shares: dict[int, float] = {i: w / total_w for i, w in weights.items()}

    broad_keys = {i for i, c in enumerate(clusters) if c.cls == "C4"}
    if broad_keys:
        shares = _water_fill_cap(shares, cfg.max_broad_share, broad_keys)

    for i, cluster in enumerate(clusters):
        cluster.allocated_share = shares[i]
        cluster.allocated_budget = shares[i] * cfg.total_budget

        for p in cluster.phrases:
            fc = forecast_index.get(p["phrase"]) or {}
            cpc = float(fc.get("avg_cpc") or 0.0)
            ctr = float(fc.get("ctr") or 0.0)
            impressions = float(fc.get("impressions") or 0.0)
            clicks = float(fc.get("clicks") or 0.0)
            p["clicks"] = int(round(clicks))
            p["impressions"] = round(impressions, 0)
            p["ctr"] = round(ctr, 2)
            p["cpc"] = round(cpc, 2)


def normalize_forecast_rows(forecast: list[dict] | dict) -> tuple[list[dict], dict]:
    if isinstance(forecast, dict):
        rows_obj = forecast.get("rows") or forecast.get("phrases") or []
        summary = dict(forecast.get("summary") or {})
    else:
        rows_obj = forecast
        summary = {}

    rows: list[dict] = []
    for item in rows_obj if isinstance(rows_obj, list) else []:
        if not isinstance(item, dict):
            continue
        phrase = normalize_phrase(str(item.get("phrase") or item.get("Phrase") or ""))
        if not phrase:
            continue
        impressions = _to_float(item.get("impressions") or item.get("Shows"))
        clicks = _to_float(item.get("clicks") or item.get("FirstPlaceClicks") or item.get("Clicks"))
        ctr = _to_float(item.get("ctr") or item.get("FirstPlaceCTR") or item.get("CTR"))
        cpc = _to_float(
            item.get("avg_cpc")
            or item.get("cpc")
            or item.get("first_place_cpc")
            or item.get("Max")
        )
        spending = _to_float(item.get("spending"))
        if cpc <= 0 and spending > 0 and clicks > 0:
            cpc = spending / clicks
        if spending <= 0 and clicks > 0 and cpc > 0:
            spending = clicks * cpc
        if ctr <= 0 and impressions > 0 and clicks > 0:
            ctr = clicks / impressions * 100.0
        rows.append(
            {
                **item,
                "phrase": phrase,
                "impressions": impressions,
                "clicks": clicks,
                "spending": round(spending, 2),
                "ctr": round(ctr, 2),
                "avg_cpc": round(cpc, 2) if cpc > 0 else None,
            }
        )
    return rows, summary


def compute_clean_cpc(rows: list[dict]) -> dict:
    samples = [
        (_to_float(row.get("avg_cpc")), max(_to_float(row.get("clicks")), 1.0))
        for row in rows
        if _to_float(row.get("avg_cpc")) > 0 and _to_float(row.get("clicks")) > 0
    ]
    if not samples:
        return {"value": 0.0, "method": "no_valid_cpc", "samples": 0}

    weighted_median = _weighted_quantile(samples, 0.5)
    p10 = _weighted_quantile(samples, 0.1)
    p90 = _weighted_quantile(samples, 0.9)
    clipped_total = 0.0
    weight_total = 0.0
    for cpc, weight in samples:
        clipped_total += min(max(cpc, p10), p90) * weight
        weight_total += weight
    winsorized_mean = clipped_total / weight_total if weight_total else weighted_median
    value = min(weighted_median, winsorized_mean) if winsorized_mean > 0 else weighted_median
    cpc_source = "direct_first_place" if any(row.get("first_place_cpc") for row in rows) else "forecast_avg_cpc"
    return {
        "value": round(value, 2),
        "weighted_median": round(weighted_median, 2),
        "winsorized_mean": round(winsorized_mean, 2),
        "method": "click_weighted_median_winsorized",
        "source": cpc_source,
        "samples": len(samples),
    }


def compute_budget_scenarios(
    rows: list[dict],
    clusters: list[ClusterResult],
    summary: dict | None = None,
    forecast_error_margin: float = 0.3,
) -> tuple[list[dict], dict, dict]:
    summary = summary or {}
    margin = max(0.0, float(forecast_error_margin or 0.0))
    clean = compute_clean_cpc(rows)
    clean_cpc = float(clean["value"] or 0.0)
    if not rows:
        scenarios = [
            {
                "id": scenario_def["id"],
                "title": scenario_def["title"],
                "budget": 0.0,
                "budget_low": 0.0,
                "budget_high": 0.0,
                "target_clicks": scenario_def.get("target_clicks"),
                "clicks": 0.0,
                "impressions": 0.0,
                "avg_cpc": 0.0,
                "coverage": 0.0,
                "scope_budget": 0.0,
                "below_viable_scope": False,
            }
            for scenario_def in _SCENARIO_DEFS
        ]
        return scenarios, clean, {
            "budget_min": 0.0,
            "budget_max": 0.0,
            "eligible_budget": 0.0,
            "clicks": 0.0,
            "impressions": 0.0,
            "source": "empty_forecast",
            "forecast_error_margin": margin,
        }
    cluster_by_phrase = {
        str(p.get("phrase")): cluster
        for cluster in clusters
        for p in cluster.phrases
    }
    demand_by_priority = {"high": 0.0, "medium": 0.0, "low": 0.0}
    clicks_by_priority = {"high": 0.0, "medium": 0.0, "low": 0.0}
    impressions_by_priority = {"high": 0.0, "medium": 0.0, "low": 0.0}

    for row in rows:
        cluster = cluster_by_phrase.get(str(row.get("phrase") or ""))
        priority = _priority_for_cluster(cluster)
        spending = _to_float(row.get("spending"))
        clicks = _to_float(row.get("clicks"))
        impressions = _to_float(row.get("impressions"))
        demand_by_priority[priority] += spending
        clicks_by_priority[priority] += clicks
        impressions_by_priority[priority] += impressions

    eligible_total = sum(demand_by_priority.values())
    common_min = _to_float(summary.get("budget_min") or summary.get("Min"))
    common_max = _to_float(summary.get("budget_max") or summary.get("Max"))
    full_budget = max(common_max, eligible_total)
    if full_budget <= 0:
        full_budget = eligible_total
    full_demand = {
        "budget_min": round(common_min if common_min > 0 else eligible_total, 2),
        "budget_max": round(full_budget, 2),
        "eligible_budget": round(eligible_total, 2),
        "clicks": int(round(sum(clicks_by_priority.values()))),
        "impressions": round(sum(impressions_by_priority.values()), 0),
        "source": "direct_common" if common_max > 0 else "phrase_sum",
        "forecast_error_margin": margin,
    }

    scenarios: list[dict] = []
    previous_budget = 0.0
    for scenario_def in _SCENARIO_DEFS:
        priorities = set(scenario_def["priorities"])
        scope_budget = sum(v for k, v in demand_by_priority.items() if k in priorities)
        if scenario_def["id"] == "full":
            raw_budget = full_budget
            target_clicks = sum(clicks_by_priority.values())
        else:
            target_clicks = float(scenario_def["target_clicks"] or 0)
            raw_budget = target_clicks * clean_cpc if clean_cpc > 0 else 0.0
        if scenario_def["id"] == "full":
            budget = _round_budget(raw_budget)
        else:
            # Scenarios are ordered by rising target_clicks, so budget should
            # rise monotonically too; this only bites if clean_cpc is 0 for a
            # scenario computed after a non-zero one, which shouldn't happen
            # since clean_cpc is constant across scenarios in one call.
            budget = _round_budget(max(previous_budget, raw_budget))
            previous_budget = budget
        clicks = budget / clean_cpc if clean_cpc > 0 else 0.0
        impressions = _scenario_impressions(rows, clicks)
        # pct_of_demand is NOT capped at 100%: a starter budget can legitimately
        # exceed the collected phrase demand for a narrow priority scope, and
        # silently clipping that to "100%" hides the discrepancy from the reader.
        pct_of_demand = round(budget / full_budget * 100.0, 1) if full_budget > 0 else None
        exceeds_demand = bool(full_budget > 0 and budget > full_budget + 1e-9)
        exceeds_demand_ratio = round(budget / full_budget, 2) if full_budget > 0 else None
        scenarios.append(
            {
                "id": scenario_def["id"],
                "title": scenario_def["title"],
                "budget": budget,
                "budget_low": round(budget * (1 - margin), 2),
                "budget_high": round(budget * (1 + margin), 2),
                "starter_budget_rub": budget,
                "demand_full_rub": round(full_budget, 2),
                "target_clicks": int(round(target_clicks)) if target_clicks else None,
                "clicks": int(round(clicks)),
                "impressions": round(impressions, 0),
                "avg_cpc": round(clean_cpc, 2),
                "coverage": round(min(budget / full_budget, 1.0), 4) if full_budget > 0 else 0.0,
                "pct_of_demand": pct_of_demand,
                "exceeds_demand": exceeds_demand,
                "exceeds_demand_ratio": exceeds_demand_ratio,
                "scope_budget": round(scope_budget, 2),
                "below_viable_scope": bool(scope_budget > 0 and budget > scope_budget),
            }
        )
    return scenarios, clean, full_demand


def apply_lead_forecast(
    scenarios: list[dict],
    expected_conversion_rate: float | None,
    cr_benchmark_low: float = 0.02,
    cr_benchmark_high: float = 0.05,
) -> list[dict]:
    """Добавляет к каждому сценарию бюджета прогноз лидов и CPL: leads = clicks * CR,
    CPL = budget / leads. Если CR сайта не задан пользователем, считает диапазон по
    среднеотраслевым бенчмаркам и помечает cr_is_estimated=True, чтобы отчёт мог
    показать точные цифры только при явно заданной конверсии."""
    is_estimated = expected_conversion_rate is None
    cr_low = cr_benchmark_low if is_estimated else expected_conversion_rate
    cr_high = cr_benchmark_high if is_estimated else expected_conversion_rate

    result: list[dict] = []
    for scenario in scenarios:
        clicks = float(scenario.get("clicks") or 0.0)
        budget = float(scenario.get("budget") or 0.0)
        leads_low = clicks * cr_low
        leads_high = clicks * cr_high
        cpl_low = budget / leads_high if leads_high > 0 else None
        cpl_high = budget / leads_low if leads_low > 0 else None
        enriched = dict(scenario)
        enriched.update(
            {
                "leads_low": round(leads_low, 1),
                "leads_high": round(leads_high, 1),
                "cpl_low": round(cpl_low, 2) if cpl_low is not None else None,
                "cpl_high": round(cpl_high, 2) if cpl_high is not None else None,
                "cr_is_estimated": is_estimated,
            }
        )
        if not is_estimated:
            leads = clicks * expected_conversion_rate
            cpl = budget / leads if leads > 0 else None
            enriched["leads"] = round(leads, 1)
            enriched["cpl"] = round(cpl, 2) if cpl is not None else None
        result.append(enriched)
    return result


def apply_rsya_forecast(
    scenarios: list[dict],
    search_clean_cpc: float,
    rsya_cpc_factor: float = 0.4,
    rsya_ctr_pct: float = 0.15,
) -> list[dict]:
    """Для каждого сценария бюджета считает оценочный прогноз для РСЯ на том же
    бюджете, через CPM и охват вместо CPC/кликов Поиска: РСЯ-CPC берётся как доля
    от очищенного CPC Поиска (площадки РСЯ дешевле), а CPM выводится из CPC и
    среднеотраслевого CTR РСЯ (CPM = CPC * CTR% * 10). Это оценка по бенчмаркам,
    а не измеренные данные — Forecast API не отдаёт отдельный прогноз для РСЯ."""
    rsya_cpc = float(search_clean_cpc or 0.0) * max(0.0, rsya_cpc_factor)
    ctr = max(0.0, rsya_ctr_pct)
    cpm = rsya_cpc * ctr * 10 if rsya_cpc > 0 else 0.0

    result: list[dict] = []
    for scenario in scenarios:
        budget = float(scenario.get("budget") or 0.0)
        clicks = budget / rsya_cpc if rsya_cpc > 0 else 0.0
        reach = clicks / (ctr / 100.0) if ctr > 0 else 0.0
        result.append(
            {
                "id": scenario.get("id"),
                "title": scenario.get("title"),
                "budget": budget,
                "cpm": round(cpm, 2),
                "cpc": round(rsya_cpc, 2),
                "reach": int(round(reach)),
                "clicks": int(round(clicks)),
            }
        )
    return result


def allocate_budget(
    keywords: list[dict],
    forecast: list[dict] | dict,
    niche: str,
    geo_tokens: set[str],
    cfg: AllocationConfig,
) -> dict:
    niche_stems = extract_niche_stems(niche)
    geo_norm = {normalize_phrase(t) for t in geo_tokens if t}
    forecast_rows, forecast_summary = normalize_forecast_rows(forecast)

    forecast_index = {
        normalize_phrase(str(item.get("phrase") or "")): item
        for item in forecast_rows
        if item.get("phrase")
    }
    if forecast_index:
        forecast_phrases = set(forecast_index)
        working_keywords = [
            kw for kw in keywords
            if normalize_phrase(str(kw.get("phrase") or "")) in forecast_phrases
        ]
    else:
        working_keywords = list(keywords)

    if cfg.exclude_informational_phrases:
        working_keywords = [
            kw for kw in working_keywords
            if classify_intent_category(str(kw.get("phrase") or "")) != "informational"
        ]

    intent_breakdown = _compute_intent_breakdown(forecast_rows)

    clusters = assign_clusters(working_keywords, niche_stems, geo_norm, cfg)
    scenarios, clean_cpc, full_demand = compute_budget_scenarios(
        forecast_rows,
        clusters,
        forecast_summary,
        forecast_error_margin=cfg.forecast_error_margin,
    )
    scenarios = apply_lead_forecast(
        scenarios,
        cfg.expected_conversion_rate,
        cfg.cr_benchmark_low,
        cfg.cr_benchmark_high,
    )
    recommended = next((s for s in scenarios if s["id"] == "recommended"), None)
    effective_budget = float(recommended.get("budget") if recommended else 0.0)
    if effective_budget <= 0 and forecast_rows:
        effective_budget = _round_budget(sum(_to_float(row.get("spending")) for row in forecast_rows))

    effective_cfg = AllocationConfig(
        total_budget=effective_budget,
        weight_center=cfg.weight_center,
        weight_transactional=cfg.weight_transactional,
        weight_characteristic=cfg.weight_characteristic,
        weight_broad=cfg.weight_broad,
        max_broad_share=cfg.max_broad_share,
        broad_bid_factor=cfg.broad_bid_factor,
        min_cluster_freq=cfg.min_cluster_freq,
        min_cluster_keys=cfg.min_cluster_keys,
        low_freq_threshold=cfg.low_freq_threshold,
    )

    basis_c4: dict[str, list[PhraseParts]] = {}
    for cluster in clusters:
        if cluster.cls == "C4":
            for p in cluster.phrases:
                parts = decompose_phrase(p["phrase"], niche_stems, geo_norm)
                basis_c4.setdefault(cluster.base, []).append(parts)

    allocate_shares(clusters, effective_cfg, forecast_index)

    all_cluster_phrases = [[p["phrase"] for p in c.phrases] for c in clusters]
    for idx, cluster in enumerate(clusters):
        if cluster.cls != "C4":
            child_parts = [
                decompose_phrase(p["phrase"], niche_stems, geo_norm)
                for p in cluster.phrases
            ]
            parent_parts = basis_c4.get(cluster.base, [])
            raw_minus_words = cross_minus(child_parts, parent_parts)
            # Guard against minus words that would silently suppress a *sibling*
            # cluster's own active phrases (e.g. minus "губ" while another
            # cluster still targets "коррекция губ").
            sibling_active_phrases = [
                phrase
                for j, phrases in enumerate(all_cluster_phrases)
                if j != idx
                for phrase in phrases
            ]
            clean_minus_words, review_minus_words = validate_minus_words(
                raw_minus_words, sibling_active_phrases
            )
            cluster.minus_words = clean_minus_words
            cluster.minus_words_review = review_minus_words

    warnings = build_guardrails(clusters, effective_cfg)
    if len(keywords) > FORECAST_KEYWORD_LIMIT:
        warnings.append(
            f"Для прогноза используется топ-{FORECAST_KEYWORD_LIMIT} очищенных фраз; "
            "остальные сохраняются как резерв семантики."
        )
    if clean_cpc.get("samples", 0) == 0 and forecast_rows:
        warnings.append("В прогнозе нет валидных кликов/CPC, бюджетные сценарии требуют ручной проверки.")
    if any(s.get("below_viable_scope") for s in scenarios if s.get("id") != "full"):
        warnings.append(
            "Прогнозная выборка ниже минимального жизнеспособного месячного запуска; "
            "стартовые сценарии рассчитаны по нижней границе бюджета, а не по сумме строк прогноза."
        )
    if recommended and (recommended.get("exceeds_demand_ratio") or 0) >= 3:
        warnings.append(
            "Бюджет установлен на минимально жизнеспособном уровне для статистической "
            "значимости показов, а не выведен из объёма собранного спроса по фразам. "
            "Фактический спрос по текущему ядру ниже этого порога "
            f"(в {recommended['exceeds_demand_ratio']:.1f}× раза)."
        )
    informational_share = intent_breakdown.get("informational", {}).get("share", 0.0)
    if informational_share > cfg.informational_share_warn_threshold:
        warnings.append(
            f"Доля информационных запросов (симптомы/диагностика/самолечение) в ядре — "
            f"{informational_share:.0%}, что превышает порог "
            f"{cfg.informational_share_warn_threshold:.0%}. Часть трафика может быть "
            "нецелевой для конверсионной кампании."
        )

    all_phrases = []
    for cluster in clusters:
        priority = _priority_for_cluster(cluster)
        for p in cluster.phrases:
            fc = forecast_index.get(normalize_phrase(str(p.get("phrase") or ""))) or {}
            forecast_clicks = _to_float(fc.get("clicks"))
            forecast_impressions = _to_float(fc.get("impressions"))
            forecast_cpc = _to_float(fc.get("avg_cpc"))
            forecast_ctr = _to_float(fc.get("ctr"))
            all_phrases.append(
                {
                    "phrase": p.get("phrase", ""),
                    "freq": p.get("freq", 0),
                    "clicks": int(round(forecast_clicks)),
                    "impressions": round(forecast_impressions, 0),
                    "ctr": round(forecast_ctr, 2),
                    "cpc": round(forecast_cpc, 2),
                    "cluster": cluster.title,
                    "priority": priority,
                    "is_center_of_gravity": cluster.is_center_of_gravity,
                    "ctr_significant": is_statistically_significant(
                        forecast_clicks, forecast_impressions
                    ),
                    "intent_category": classify_intent_category(str(p.get("phrase") or "")),
                }
            )
    priority_order = {"high": 0, "medium": 1, "low": 2}
    all_phrases.sort(
        key=lambda x: (
            priority_order.get(str(x.get("priority")), 9),
            -_to_float(x.get("clicks")),
            -_to_float(x.get("impressions")),
            -_to_float(x.get("freq")),
        )
    )
    top_phrases = all_phrases[:10]

    total_clicks = _to_float(recommended.get("clicks") if recommended else 0)
    total_impressions = _to_float(recommended.get("impressions") if recommended else 0)
    avg_cpc = _to_float(recommended.get("avg_cpc") if recommended else clean_cpc["value"])
    avg_ctr = (
        round(total_clicks / total_impressions * 100.0, 2) if total_impressions > 0 else 0.0
    )

    rsya_forecast: list[dict] = []
    if cfg.campaign_type in ("rsya", "both"):
        rsya_forecast = apply_rsya_forecast(
            scenarios,
            float(clean_cpc.get("value") or 0.0),
            cfg.rsya_cpc_factor,
            cfg.rsya_ctr_pct,
        )

    return {
        "methodology_version": METHODOLOGY_VERSION,
        "total_budget": effective_budget,
        "recommended_budget": effective_budget,
        "campaign_type": cfg.campaign_type,
        "rsya_forecast": rsya_forecast,
        "forecast_error_margin": cfg.forecast_error_margin,
        "intent_breakdown": intent_breakdown,
        "budget_scenarios": scenarios,
        "clean_cpc": clean_cpc,
        "full_demand": full_demand,
        "forecast_rows": forecast_rows,
        "forecasted_keywords": len(forecast_rows),
        "excluded_keywords": max(0, len(keywords) - len(working_keywords)),
        "clusters": [
            {
                "base": c.base,
                "title": c.title,
                "type": c.type,
                "cls": c.cls,
                "priority": _priority_for_cluster(c),
                "is_center_of_gravity": c.is_center_of_gravity,
                "n_keys": c.n_keys,
                "total_freq": c.total_freq,
                "allocated_share": round(c.allocated_share, 4),
                "allocated_budget": round(c.allocated_budget, 2),
                "minus_words": c.minus_words,
                "minus_words_review": c.minus_words_review,
                "phrases": [
                    {"phrase": p.get("phrase", ""), "freq": p.get("freq", 0)}
                    for p in c.phrases
                ],
            }
            for c in clusters
        ],
        "warnings": warnings,
        "top_phrases": top_phrases,
        "total_impressions": round(total_impressions, 0),
        "total_clicks": int(round(total_clicks)),
        "avg_cpc": avg_cpc,
        "avg_ctr": avg_ctr,
    }


def _priority_for_cluster(cluster: ClusterResult | None) -> str:
    if cluster is None:
        return "low"
    if cluster.cls in {"C1", "C2"} or cluster.is_center_of_gravity:
        return "high"
    if cluster.cls == "C3":
        return "medium"
    return "low"


def _weighted_quantile(samples: list[tuple[float, float]], quantile: float) -> float:
    ordered = sorted(samples, key=lambda item: item[0])
    total_weight = sum(weight for _, weight in ordered)
    if total_weight <= 0:
        return 0.0
    threshold = total_weight * quantile
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= threshold:
            return value
    return ordered[-1][0]


def _round_budget(value: float) -> float:
    if value <= 0:
        return 0.0
    step = 1000.0 if value >= 10000 else 500.0
    return round(value / step) * step


def _scenario_impressions(rows: list[dict], scenario_clicks: float) -> float:
    row_clicks = sum(_to_float(row.get("clicks")) for row in rows)
    row_impressions = sum(_to_float(row.get("impressions")) for row in rows)
    if row_clicks <= 0 or row_impressions <= 0:
        return 0.0
    return scenario_clicks / row_clicks * row_impressions


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
