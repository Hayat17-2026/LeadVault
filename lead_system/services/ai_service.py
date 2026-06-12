import json
import re

def classify_lead(name: str, snippet: str, interests: str, keywords: list) -> dict:
    """
    AI Classification using rule-based NLP + scoring.
    Analyzes lead data and returns interest tags, quality tier, and recommendation.
    (For full Claude API integration, see the commented section below)
    """
    text = f"{name} {snippet} {interests}".lower()

    # ── Interest detection ────────────────────────────────────────────────────
    CATEGORIES = {
        "📱 Phones & Mobile":     ["phone", "mobile", "smartphone", "iphone", "samsung", "huawei", "android"],
        "💻 Laptops & Computers": ["laptop", "notebook", "computer", "macbook", "dell", "hp", "lenovo", "asus"],
        "🔌 Electronics":        ["electronics", "gadget", "device", "charger", "cable", "battery", "tech"],
        "⌚ Smart Devices":       ["smart", "iot", "smartwatch", "alexa", "airpods", "wearable", "tablet"],
        "👗 Fashion & Clothing":  ["fashion", "clothing", "apparel", "wear", "dress", "shoes", "style"],
        "🏪 Wholesale / B2B":     ["wholesale", "distributor", "bulk", "b2b", "supplier", "dealer", "reseller"],
        "🌐 Online Seller":       ["online", "ecommerce", "shop", "store", "delivery", "shipping"],
    }

    detected = []
    for category, terms in CATEGORIES.items():
        if any(t in text for t in terms):
            detected.append(category)

    # Add user keywords as tags
    for kw in keywords:
        tag = f"🔍 {kw.title()}"
        if kw.lower() in text and tag not in detected:
            detected.append(tag)

    if not detected:
        detected = ["📦 General Business"]

    # ── Quality scoring ───────────────────────────────────────────────────────
    quality_score = 0
    reasons       = []

    # Keyword relevance
    kw_hits = sum(1 for kw in keywords if kw.lower() in text)
    quality_score += min(kw_hits * 15, 40)
    if kw_hits > 0:
        reasons.append(f"Matched {kw_hits} keyword(s)")

    # Business signals
    b2b_terms = ["wholesale", "distributor", "b2b", "supplier", "bulk", "reseller"]
    if any(t in text for t in b2b_terms):
        quality_score += 20
        reasons.append("B2B / wholesale signal detected")

    # Contact info signals (passed from lead)
    if "email" in interests or "@" in text:
        quality_score += 15
        reasons.append("Email contact available")
    if any(c.isdigit() for c in text[:100]):
        quality_score += 10
        reasons.append("Phone number detected")

    # Activity signal
    active_terms = ["active", "online", "open", "available", "contact", "call"]
    if any(t in text for t in active_terms):
        quality_score += 10
        reasons.append("Active business signals")

    quality_score = min(quality_score, 100)

    # ── Tier ─────────────────────────────────────────────────────────────────
    if quality_score >= 75:
        tier = "🟢 High Priority"
        recommendation = "Contact immediately — strong match for your target market."
    elif quality_score >= 50:
        tier = "🟡 Medium Priority"
        recommendation = "Worth pursuing — moderate relevance to your keywords."
    else:
        tier = "🔴 Low Priority"
        recommendation = "Low relevance — consider skipping or revisit later."

    return {
        "interests":      detected,
        "quality_score":  quality_score,
        "tier":           tier,
        "recommendation": recommendation,
        "reasons":        reasons,
    }


def classify_batch(leads: list, keywords: list) -> list:
    """Classify a list of leads and return them enriched with AI tags."""
    enriched = []
    for lead in leads:
        ai = classify_lead(
            name     = lead.get("name", ""),
            snippet  = lead.get("snippet", "") or lead.get("interests", ""),
            interests= lead.get("interests", ""),
            keywords = keywords
        )
        enriched.append({**lead, "ai": ai})
    return enriched
