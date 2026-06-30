from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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
    max_phrase_share: float = 0.15
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
            max_phrase_share=float(getattr(settings, "ALLOC_MAX_PHRASE_SHARE", 0.15)),
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
    for p in child_parts:
        child_tokens.update(p.transactional)
        child_tokens.update(p.characteristic)
    parent_tokens: set[str] = set()
    for p in parent_parts:
        parent_tokens.update(p.transactional)
        parent_tokens.update(p.characteristic)
    return sorted(child_tokens - parent_tokens)


def build_guardrails(clusters: list[ClusterResult], cfg: AllocationConfig) -> list[str]:
    warnings: list[str] = []
    broad_total = sum(c.allocated_share for c in clusters if c.type == "general")
    if broad_total > cfg.max_broad_share + 1e-9:
        warnings.append(
            f"⚠ Центр тяжести смещён на голый базис (общие фразы получают "
            f"{broad_total:.0%}), нужно углубление семантики"
        )
    overloaded = [
        p["phrase"]
        for c in clusters
        for p in c.phrases
        if p.get("phrase_share", 0.0) > cfg.max_phrase_share + 1e-9
    ]
    if overloaded:
        warnings.append(
            "⚠ Перегруженные фразы (>15% бюджета кластера): " + ", ".join(overloaded[:5])
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
                if total_freq < cfg.min_cluster_freq or len(items) < cfg.min_cluster_keys:
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

        phrase_weights: dict[int, float] = {}
        for j, p in enumerate(cluster.phrases):
            fc = forecast_index.get(p["phrase"])
            phrase_weights[j] = float(fc["clicks"]) if fc and fc.get("clicks") else 1.0

        pw_total = sum(phrase_weights.values()) or 1.0
        phrase_shares: dict[int, float] = {j: w / pw_total for j, w in phrase_weights.items()}
        phrase_shares = _water_fill_phrase_cap(phrase_shares, cfg.max_phrase_share)

        for j, p in enumerate(cluster.phrases):
            ps = phrase_shares[j]
            p["phrase_share"] = ps
            p["allocated_budget"] = ps * cluster.allocated_budget

            fc = forecast_index.get(p["phrase"]) or {}
            cpc = float(fc.get("avg_cpc") or 0.0)
            ctr = float(fc.get("ctr") or 0.0)
            adj = adjusted_cpc(cluster.cls, cpc, cfg)
            clicks, impressions = _compute_phrase_metrics(p["allocated_budget"], adj, ctr)
            p["clicks"] = round(clicks, 2)
            p["impressions"] = round(impressions, 2)
            p["ctr"] = round(ctr, 2)
            p["cpc"] = round(adj, 2)


def allocate_budget(
    keywords: list[dict],
    forecast: list[dict],
    niche: str,
    geo_tokens: set[str],
    cfg: AllocationConfig,
) -> dict:
    niche_stems = extract_niche_stems(niche)
    geo_norm = {normalize_phrase(t) for t in geo_tokens if t}

    forecast_index = {
        normalize_phrase(str(item.get("phrase") or "")): item
        for item in forecast
        if item.get("phrase")
    }

    clusters = assign_clusters(keywords, niche_stems, geo_norm, cfg)

    # Collect C4 phrases per basis for cross-minus computation
    basis_c4: dict[str, list[PhraseParts]] = {}
    for cluster in clusters:
        if cluster.cls == "C4":
            for p in cluster.phrases:
                parts = decompose_phrase(p["phrase"], niche_stems, geo_norm)
                basis_c4.setdefault(cluster.base, []).append(parts)

    allocate_shares(clusters, cfg, forecast_index)

    for cluster in clusters:
        if cluster.cls != "C4":
            child_parts = [
                decompose_phrase(p["phrase"], niche_stems, geo_norm)
                for p in cluster.phrases
            ]
            parent_parts = basis_c4.get(cluster.base, [])
            cluster.minus_words = cross_minus(child_parts, parent_parts)

    warnings = build_guardrails(clusters, cfg)

    all_phrases = [
        {
            **p,
            "spending": p.get("allocated_budget", 0.0),
            "cluster": cluster.title,
            "is_center_of_gravity": cluster.is_center_of_gravity,
        }
        for cluster in clusters
        for p in cluster.phrases
    ]
    all_phrases.sort(key=lambda x: x.get("allocated_budget", 0.0), reverse=True)
    top_phrases = all_phrases[:10]

    total_clicks = sum(p.get("clicks", 0.0) for p in all_phrases)
    total_impressions = sum(p.get("impressions", 0.0) for p in all_phrases)
    avg_cpc = round(cfg.total_budget / total_clicks, 2) if total_clicks > 0 else 0.0
    avg_ctr = (
        round(total_clicks / total_impressions * 100.0, 2) if total_impressions > 0 else 0.0
    )

    return {
        "total_budget": cfg.total_budget,
        "clusters": [
            {
                "base": c.base,
                "title": c.title,
                "type": c.type,
                "cls": c.cls,
                "is_center_of_gravity": c.is_center_of_gravity,
                "n_keys": c.n_keys,
                "total_freq": c.total_freq,
                "allocated_share": round(c.allocated_share, 4),
                "allocated_budget": round(c.allocated_budget, 2),
                "minus_words": c.minus_words,
                "phrases": c.phrases,
            }
            for c in clusters
        ],
        "warnings": warnings,
        "top_phrases": top_phrases,
        "total_impressions": round(total_impressions, 0),
        "total_clicks": round(total_clicks, 2),
        "avg_cpc": avg_cpc,
        "avg_ctr": avg_ctr,
    }
