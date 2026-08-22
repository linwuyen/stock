#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "research-voi.json"

EVIDENCE_GATES = {
    "score_complete",
    "freshness",
    "evidence",
    "benchmark_freshness",
    "benchmark_evidence",
    "valuation_complete",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def clamp01(x):
    return max(0.0, min(1.0, float(x)))


def shortfall(value, threshold, scale):
    if value is None:
        return 1.0
    return clamp01(max(0.0, threshold - float(value)) / scale)


def build():
    alpha = load("data/alpha.json")
    policy = alpha["decision_policy"]
    thresholds = {
        "score": float(alpha["methodology"]["buy_gate"]),
        "confidence": float(policy["min_confidence_score"]),
        "base_upside": float(policy["min_base_upside_pct"]),
        "alpha_spread": float(policy["min_alpha_spread_pct"]),
    }

    rows = []
    for stock in alpha.get("stocks", []):
        gate = stock.get("buy_gate") or {}
        failed = list(gate.get("failed") or [])
        missing_factors = list((stock.get("score_coverage") or {}).get("missing_factors") or [])
        metrics = stock.get("valuation_metrics") or {}
        confidence = stock.get("confidence_score")
        score = stock.get("score")
        base_upside = metrics.get("base_upside_pct")
        alpha_spread = stock.get("alpha_spread_pct")

        economic_shortfalls = {
            "score": shortfall(score, thresholds["score"], 35),
            "confidence": shortfall(confidence, thresholds["confidence"], 35),
            "base_upside": shortfall(base_upside, thresholds["base_upside"], 35),
            "alpha_spread": shortfall(alpha_spread, thresholds["alpha_spread"], 40),
        }
        avg_shortfall = sum(economic_shortfalls.values()) / len(economic_shortfalls)
        gate_proximity = 1.0 - avg_shortfall

        evidence_failed = [x for x in failed if x in EVIDENCE_GATES or x == "score_complete"]
        evidence_gap = clamp01(
            0.18 * len(evidence_failed)
            + 0.22 * len(missing_factors)
            + (0.15 if not (stock.get("freshness") or {}).get("ok", False) else 0.0)
        )
        model_uncertainty = clamp01(
            (100.0 - float(confidence or 0)) / 100.0
            + 0.12 * len(missing_factors)
        )
        actionable_question = bool(stock.get("next_check") or missing_factors or evidence_failed)
        researchability = 1.0 if actionable_question else 0.35

        # This is a deterministic research-priority proxy, not a probability of
        # decision change and not a security score.
        priority = 100.0 * (
            0.40 * gate_proximity
            + 0.35 * evidence_gap
            + 0.15 * model_uncertainty
            + 0.10 * researchability
        )
        priority = round(max(0.0, min(100.0, priority)), 1)

        blockers = []
        if evidence_failed:
            blockers.append("evidence/freshness")
        if economic_shortfalls["score"] > 0:
            blockers.append("score")
        if economic_shortfalls["base_upside"] > 0:
            blockers.append("base_upside")
        if economic_shortfalls["alpha_spread"] > 0:
            blockers.append("alpha_spread")
        if economic_shortfalls["confidence"] > 0:
            blockers.append("confidence")

        rows.append({
            "ticker": stock.get("ticker"),
            "name": stock.get("name"),
            "upstream_action": stock.get("action"),
            "research_priority": priority,
            "research_lane": (
                "EVIDENCE_CLOSURE"
                if evidence_failed and sum(v > 0 for v in economic_shortfalls.values()) <= 1
                else "DECISION_REASSESSMENT"
            ),
            "gate_proximity": round(gate_proximity * 100, 1),
            "evidence_gap": round(evidence_gap * 100, 1),
            "model_uncertainty": round(model_uncertainty * 100, 1),
            "failed_buy_gate_checks": failed,
            "missing_factors": missing_factors,
            "economic_shortfalls": {k: round(v * 100, 1) for k, v in economic_shortfalls.items()},
            "blocker_classes": blockers,
            "next_question": stock.get("next_check") or stock.get("invalidation_condition"),
            "guardrail": "Research priority cannot create or upgrade BUY authority.",
        })

    rows.sort(key=lambda x: (-x["research_priority"], x["ticker"] or ""))
    for i, row in enumerate(rows, 1):
        row["rank"] = i

    return {
        "schema_version": 1,
        "as_of": alpha["meta"].get("decision_as_of") or alpha["meta"].get("as_of"),
        "contract": "non_authoritative-value-of-information-research-priority-v1",
        "authority": False,
        "score_influence": False,
        "buy_gate_influence": False,
        "method": (
            "Ranks already-researched securities by decision-boundary proximity, "
            "evidence/freshness gaps, model uncertainty and whether a concrete next "
            "question exists. It is a research scheduling proxy, not a probability "
            "of decision change and not a capital-sizing model."
        ),
        "weights": {
            "gate_proximity": 0.40,
            "evidence_gap": 0.35,
            "model_uncertainty": 0.15,
            "researchability": 0.10
        },
        "rows": rows
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    built = build()
    if args.check:
        current = json.loads(OUT.read_text(encoding="utf-8"))
        assert current == built, "research-voi.json is stale"
        print("research VOI PASS")
    else:
        OUT.write_text(json.dumps(built, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(OUT)


if __name__ == "__main__":
    main()
