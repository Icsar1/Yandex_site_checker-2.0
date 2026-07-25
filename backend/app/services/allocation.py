from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.keywords import (
    COMMERCIAL_MARKERS,
    _RU_STOPWORDS,
    _marker_matches,
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
        "min_budget": 30000.0,
        "priorities": {"high"},
    },
    {
        "id": "recommended",
        "title": "Рекомендуемый старт",
        "target_clicks": 100,
        "min_budget": 60000.0,
        "priorities": {"high", "medium"},
    },
    {
        "id": "confident",
        "title": "Уверенный запуск",
        "target_clicks": 150,
        "min_budget": 100000.0,
        "priorities": {"high", "medium", "low"},
    },
    {
        "id": "full",
        "title": "Полный спрос",
        "target_clicks": None,
        "min_budget": 0.0,
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

    @classmethod
    def from_settings(cls, settings: object) -> "AllocationConfig":
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
                    title=f"{basis_key} / {cluster_type}",
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
                title="малопоказы / general",
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
) -> tuple[list[dict], dict, dict]:
    summary = summary or {}
    clean = compute_clean_cpc(rows)
    clean_cpc = float(clean["value"] or 0.0)
    if not rows:
        scenarios = [
            {
                "id": scenario_def["id"],
                "title": scenario_def["title"],
                "budget": 0.0,
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
            click_budget = target_clicks * clean_cpc if clean_cpc > 0 else 0.0
            raw_budget = max(click_budget, float(scenario_def.get("min_budget") or 0.0))
        if scenario_def["id"] == "full":
            budget = _round_budget(raw_budget)
        else:
            budget = _round_budget(max(previous_budget, raw_budget))
            previous_budget = budget
        clicks = budget / clean_cpc if clean_cpc > 0 else 0.0
        impressions = _scenario_impressions(rows, clicks)
        scenarios.append(
            {
                "id": scenario_def["id"],
                "title": scenario_def["title"],
                "budget": budget,
                "target_clicks": int(round(target_clicks)) if target_clicks else None,
                "clicks": int(round(clicks)),
                "impressions": round(impressions, 0),
                "avg_cpc": round(clean_cpc, 2),
                "coverage": round(min(budget / full_budget, 1.0), 4) if full_budget > 0 else 0.0,
                "scope_budget": round(scope_budget, 2),
                "below_viable_scope": bool(scope_budget > 0 and budget > scope_budget),
            }
        )
    return scenarios, clean, full_demand


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

    clusters = assign_clusters(working_keywords, niche_stems, geo_norm, cfg)
    scenarios, clean_cpc, full_demand = compute_budget_scenarios(
        forecast_rows,
        clusters,
        forecast_summary,
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

    for cluster in clusters:
        if cluster.cls != "C4":
            child_parts = [
                decompose_phrase(p["phrase"], niche_stems, geo_norm)
                for p in cluster.phrases
            ]
            parent_parts = basis_c4.get(cluster.base, [])
            cluster.minus_words = cross_minus(child_parts, parent_parts)

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

    return {
        "methodology_version": METHODOLOGY_VERSION,
        "total_budget": effective_budget,
        "recommended_budget": effective_budget,
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
