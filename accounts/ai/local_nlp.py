# accounts/ai/local_nlp.py
import re
from datetime import date, datetime, timedelta
from difflib import get_close_matches
from typing import Dict, Optional, Tuple, List

from accounts.models import Branch, Product


# ---------------------------
# Normalization Utilities
# ---------------------------
_WHITESPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s\-:/]")  # keep hyphen/colon/slash to parse dates and SKUs

def normalize(text: str) -> str:
    text = (text or "").lower()
    text = _PUNCT.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text


# ---------------------------
# Date Parsing
# ---------------------------
_DATE_RE = re.compile(r"\b(\d{4})[-/](\d{2})[-/](\d{2})\b")  # 2026-03-18 or 2026/03/18

def _week_start(d: date) -> date:
    # Monday as start (align with many BI conventions); change to Sunday if needed
    return d - timedelta(days=d.weekday())

def detect_date_range(q: str) -> Tuple[Optional[date], Optional[date], Optional[str]]:
    """
    Attempts to derive a date range (since, until) from natural language.
    Returns (since, until, label)
    If not found, returns (None, None, None).
    Supports: today, yesterday, last 7 days, last 14 days, this week, last week, this month, last month,
    explicit 'YYYY-MM-DD' (single) or 'YYYY-MM-DD to YYYY-MM-DD'.
    """
    qn = normalize(q)
    today = date.today()

    # explicit range "YYYY-MM-DD to YYYY-MM-DD"
    if " to " in qn:
        parts = qn.split(" to ")
        if len(parts) == 2:
            m1 = _DATE_RE.search(parts[0])
            m2 = _DATE_RE.search(parts[1])
            if m1 and m2:
                d1 = date(int(m1.group(1)), int(m1.group(2)), int(m1.group(3)))
                d2 = date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
                if d1 <= d2:
                    return d1, d2, f"{d1}→{d2}"

    # single explicit date
    m = _DATE_RE.search(qn)
    if m:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d, d, str(d)

    # common relative phrases
    if re.search(r"\btoday\b", qn):
        return today, today, "today"
    if re.search(r"\byesterday\b", qn):
        y = today - timedelta(days=1)
        return y, y, "yesterday"

    if re.search(r"\blast\s*7\s*days\b|\bpast\s*7\s*days\b|\bweek\b", qn) and "this week" not in qn and "last week" not in qn:
        since = today - timedelta(days=6)
        return since, today, "last_7_days"

    if re.search(r"\blast\s*14\s*days\b|\bpast\s*14\s*days\b", qn):
        since = today - timedelta(days=13)
        return since, today, "last_14_days"

    if re.search(r"\bthis week\b", qn):
        ws = _week_start(today)
        return ws, today, "this_week"

    if re.search(r"\blast week\b", qn):
        ws = _week_start(today) - timedelta(days=7)
        we = ws + timedelta(days=6)
        return ws, we, "last_week"

    if re.search(r"\bthis month\b", qn):
        first = today.replace(day=1)
        return first, today, "this_month"

    if re.search(r"\blast month\b", qn):
        first_this = today.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start, last_month_end, "last_month"

    return None, None, None


# ---------------------------
# Entity Extraction
# ---------------------------
def extract_branch(q: str) -> Optional[str]:
    """
    Best-effort branch matching by name (fuzzy).
    Returns the matched branch.name or None.
    """
    qn = normalize(q)
    branches = list(Branch.objects.values_list("name", flat=True))
    if not branches:
        return None
    # exact-ish mention
    for b in branches:
        if normalize(b) in qn:
            return b
    # fuzzy top-1
    close = get_close_matches(qn, [normalize(b) for b in branches], n=1, cutoff=0.8)
    if close:
        # map back to original string
        norm_to_orig = {normalize(b): b for b in branches}
        return norm_to_orig.get(close[0])
    return None

def extract_product(q: str) -> Optional[Dict[str, str]]:
    """
    Try to find a product by SKU or name. Returns dict like:
        {"sku": "..."} or {"name": "..."} or {"id": <int>}
    Strategy:
      1) direct SKU token match (alnum with dashes)
      2) icontains by SKU/name (cheap top-1)
      3) fuzzy by name (difflib; use cautiously)
    """
    qn = normalize(q)
    tokens = qn.split()

    # 1) Look for exact-ish SKU-like token (alphanumeric or hyphen)
    for t in tokens:
        if re.match(r"^[a-z0-9\-]+$", t):
            pr = Product.objects.filter(sku__iexact=t).values("id", "sku", "name")[:1]
            if pr:
                return {"id": pr[0]["id"], "sku": pr[0]["sku"], "name": pr[0]["name"]}

    # 2) Try icontains search (name/sku)
    pr = Product.objects.filter(sku__icontains=qn).values("id", "sku", "name")[:1]
    if pr:
        return {"id": pr[0]["id"], "sku": pr[0]["sku"], "name": pr[0]["name"]}

    pr = Product.objects.filter(name__icontains=qn).values("id", "sku", "name")[:1]
    if pr:
        return {"id": pr[0]["id"], "sku": pr[0]["sku"], "name": pr[0]["name"]}

    # 3) Fuzzy by name (load top N names; watch performance)
    names = list(Product.objects.values_list("name", flat=True)[:500])  # cap for performance
    if names:
        close = get_close_matches(qn, [normalize(n) for n in names], n=1, cutoff=0.85)
        if close:
            norm_to_orig = {normalize(n): n for n in names}
            name = norm_to_orig[close[0]]
            pr = Product.objects.filter(name=name).values("id", "sku", "name")[:1]
            if pr:
                return {"id": pr[0]["id"], "sku": pr[0]["sku"], "name": pr[0]["name"]}

    return None


# ---------------------------
# Intent Scoring
# ---------------------------
INTENT_PATTERNS = {
    "top_products": {
        "any": [
            (r"\btop (?:\d+ )?(products|items)\b", 3.0),
            (r"\bbest (?:selling )?(products|items)\b", 3.0),
            (r"\btop sellers?\b", 2.5),
            (r"\btop 5\b", 2.0),
        ],
        "keywords": [
            ("top", 1.0), ("best", 0.8), ("sell", 0.6), ("popular", 0.6), ("rank", 0.5)
        ],
    },
    "low_stock": {
        "any": [
            (r"\blow stock\b", 3.0),
            (r"\blow on stock\b", 3.0),
            (r"\bout of stock\b", 2.5),
            (r"\bstock shortage\b", 2.0),
        ],
        "keywords": [("stock", 0.6), ("reorder", 0.4), ("low", 0.4), ("alert", 0.3)],
    },
    "sales_today": {
        "any": [
            # already present:
            (r"\b(sales?|revenue).*(today|for today|today's)\b", 3.0),
            (r"\bhow much.*(sold|sales).*today\b", 3.0),

            # NEW: relative ranges
            (r"\b(sales?|revenue).*(last|past)\s*\d+\s*days\b", 3.0),
            (r"\b(sales?|revenue).*(this|last)\s*week\b", 2.8),
            (r"\b(sales?|revenue).*(this|last)\s*month\b", 2.8),
            (r"\b(sales?|revenue).*(yesterday)\b", 2.8),
            # Optional additional coverage:
            (r"\bturnover\b.*(today|yesterday|last|past)\b", 2.4),
        ],
        "keywords": [
            ("sales", 0.8), ("revenue", 0.8),
            ("today", 0.5), ("yesterday", 0.4),
            ("last", 0.4), ("past", 0.4), ("days", 0.3), ("week", 0.3), ("month", 0.3),
        ],
    },

    "branch_rank": {
        "any": [
            (r"\bwhich branch (?:is|was) (?:best|top)\b", 3.0),
            (r"\bbranch.*(rank|ranking|leaderboard)\b", 2.5),
            (r"\btop branches\b", 2.0),
        ],
        "keywords": [("branch", 0.6), ("rank", 0.6), ("best", 0.5), ("top", 0.5)],
    },
    "reorder_recommendations": {
        "any": [
            (r"\bwhat should i (reorder|restock|buy more)\b", 3.0),
            (r"\breorder (?:recommendations|suggestions)\b", 3.0),
            (r"\bitems to (?:reorder|restock)\b", 2.5),
        ],
        "keywords": [("reorder", 0.8), ("restock", 0.8), ("purchase", 0.6)],
    },
}
INTENT_PATTERNS["sales_today"]["any"].append((r"\bturnover\b.*\btoday\b", 2.5))
INTENT_PATTERNS["top_products"]["keywords"].append(("fast movers", 0.8))

def score_intent(q: str, intent_key: str) -> float:
    """
    Weighted scoring: sum of regex hits + keyword presence.
    """
    cfg = INTENT_PATTERNS[intent_key]
    score = 0.0

    # regex patterns (any)
    for pat, w in cfg.get("any", []):
        if re.search(pat, q):
            score += w

    # keywords
    for kw, w in cfg.get("keywords", []):
        if kw in q:
            score += w

    return score


def parse_intent_and_entities(question: str) -> Dict:
    """
    Main entry. Returns:
      {"intent": "<intent>", "entities": {branch?, product?, since?, until?, date_label?}}
    """
    qn = normalize(question)

    # 1) Date range
    since, until, date_label = detect_date_range(qn)

    # 2) Entities (branch, product)
    branch_name = extract_branch(qn)
    product_info = extract_product(qn)

    # 3) Intent scoring
    best_intent = "unknown"
    best_score = 0.0
    for intent in INTENT_PATTERNS.keys():
        s = score_intent(qn, intent)
        if s > best_score:
            best_score = s
            best_intent = intent

    # Minimal floor to avoid random matches
    if best_score < 1.2:
        best_intent = "unknown"

    entities = {}
    if branch_name:
        entities["branch"] = branch_name
    if product_info:
        # You can pass id for precision; keep name for readability
        entities["product_id"] = product_info.get("id")
        entities["product_sku"] = product_info.get("sku")
        entities["product_name"] = product_info.get("name")

    if since and until:
        entities["since"] = since.isoformat()
        entities["until"] = until.isoformat()
        entities["date_label"] = date_label

    return {"intent": best_intent, "entities": entities}

def parse_intent_and_entities(question: str) -> Dict:
    qn = normalize(question)

    # 1) Date range
    since, until, date_label = detect_date_range(qn)

    # 2) Entities (branch, product)
    branch_name = extract_branch(qn)
    product_info = extract_product(qn)

    # 3) Intent scoring
    best_intent = "unknown"
    best_score = 0.0
    for intent in INTENT_PATTERNS.keys():
        s = score_intent(qn, intent)
        if s > best_score:
            best_score = s
            best_intent = intent

    # Minimal floor to avoid random matches
    if best_score < 1.2:
        best_intent = "unknown"

    # ---------- NEW: semantic fallback ----------
    # If we have a date range and the user mentions sales/revenue,
    # treat it as a sales aggregation intent even if patterns were not strong enough.
    if best_intent == "unknown" and (since and until) and (("sales" in qn) or ("revenue" in qn) or ("turnover" in qn)):
        best_intent = "sales_today"
    # -------------------------------------------

    entities = {}
    if branch_name:
        entities["branch"] = branch_name
    if product_info:
        entities["product_id"] = product_info.get("id")
        entities["product_sku"] = product_info.get("sku")
        entities["product_name"] = product_info.get("name")
    if since and until:
        entities["since"] = since.isoformat()
        entities["until"] = until.isoformat()
        entities["date_label"] = date_label

    return {"intent": best_intent, "entities": entities}