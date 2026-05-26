"""Entity extraction and replacement-pair generation for conflict injection."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Import the hand-curated replacement dict from injection_utils so the saved
# entity_replacements.json always includes those entries as a baseline.
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
try:
    from injection_utils import ENTITY_REPLACEMENTS as CURATED_REPLACEMENTS
except ImportError:
    CURATED_REPLACEMENTS: Dict[str, str] = {}

ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:[\s-][A-Z][a-z]+){0,3}\b")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,8}\b")
CODE_RE = re.compile(r"\b[A-Z][0-9][A-Za-z0-9+\-]*\b")

DEFAULT_ENTITY_REPLACEMENTS_PATH = Path("data/interim/entity_replacements.json")

STOP_ENTITIES = {
    # Articles / pronouns / conjunctions
    "The", "This", "That", "These", "Those", "It", "We", "You", "He", "She", "They",
    "In", "Or", "An", "As", "At", "By", "To", "Of", "On", "Is", "If", "For", "With",
    "From", "And", "But", "Not", "Are", "Was", "Has", "Had", "Its",
    # Question / relative words
    "If", "When", "Where", "What", "Which", "Who", "How", "Why", "Whether",
    # Common adverbs / discourse markers
    "Yes", "No", "Here", "There", "Also", "Additionally", "However", "Therefore",
    "According", "Based", "Please", "Thank", "Thanks", "Hello", "Hi",
    # Generic adjectives that appear title-cased in outputs
    "High", "Low", "Good", "Bad", "New", "Old", "Cool", "Hot", "Fast", "Slow",
    "Big", "Small", "Large", "Full", "Free", "Open", "Close", "Next", "Last",
    "Top", "Best", "Real", "True", "False", "Easy", "Hard", "Safe", "Ready",
    "Live", "Dark", "Light", "Deep", "Long", "Short", "Wide", "Rich", "Poor",
    "Standard", "Regular", "Basic", "Advanced", "Premium", "Classic", "Ultimate",
    "Simple", "Smart", "Clean", "Bold", "Clear", "Bright", "Sharp", "Super",
    "Ultra", "Mini", "Plus", "Pro", "Max", "Prime", "Core",
    # Generic nouns that appear capitalized
    "Jazz", "Rock", "Pop", "Blues", "Soul", "Folk", "Metal", "Club", "Team",
    "Match", "Game", "Play", "Move", "Step", "Note", "Link", "Code", "Item",
    "Type", "Mode", "Rule", "Role", "Plan", "View", "Page", "File", "Data",
    "Info", "Name", "Date", "Time", "Today", "Week", "Month", "Year", "Day",
    "Home", "Work", "Life", "World", "Place", "Point", "Level", "Group", "Area",
    "Side", "Line", "List", "Text", "Post", "Chat", "Call", "Help", "Style",
    "Deal", "Case", "Part", "Test", "Term", "Rate", "Cost", "Fee", "Tax",
    "Version", "Update", "Release",
    # Discourse / assistant phrases
    "Feel", "Free", "Assistant", "User", "Tool", "Hopefully", "Certainly",
    "Actually", "Currently", "Typically", "Generally", "Overall", "Finally",
    # API / tech generic
    "API", "Status", "Success", "Error", "Details", "Results", "Report",
    "Validation", "Order", "Number", "Response", "Request", "Query", "Event",
    "Action", "Object", "Value", "Field", "Property", "Feature", "Content",
    # Corporate suffixes
    "Inc", "Ltd", "LLC", "Corp",
    # Days
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    # Months
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
}

# Semantic sub-category sets — used to assign fine-grained buckets
# so pairing stays within semantically compatible groups.
COUNTRY_TOKENS = {
    "Afghanistan", "Albania", "Algeria", "Argentina", "Armenia", "Australia",
    "Austria", "Azerbaijan", "Bangladesh", "Belarus", "Belgium", "Bolivia",
    "Brazil", "Bulgaria", "Cambodia", "Cameroon", "Canada", "Chile", "Colombia",
    "Croatia", "Cuba", "Czech", "Denmark", "Ecuador", "Egypt", "Estonia",
    "Ethiopia", "Finland", "France", "Georgia", "Germany", "Ghana", "Greece",
    "Guatemala", "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iran",
    "Iraq", "Ireland", "Israel", "Italy", "Jamaica", "Japan", "Jordan",
    "Kazakhstan", "Kenya", "Kuwait", "Latvia", "Lebanon", "Libya", "Lithuania",
    "Malaysia", "Mexico", "Moldova", "Mongolia", "Morocco", "Myanmar",
    "Netherlands", "Nicaragua", "Nigeria", "Norway", "Pakistan", "Panama",
    "Paraguay", "Peru", "Philippines", "Poland", "Portugal", "Romania", "Russia",
    "Rwanda", "Saudi", "Serbia", "Singapore", "Slovakia", "Slovenia", "Somalia",
    "Spain", "Sudan", "Sweden", "Switzerland", "Syria", "Taiwan", "Thailand",
    "Tunisia", "Turkey", "Uganda", "Ukraine", "Uruguay", "Venezuela", "Vietnam",
    "Yemen", "Zimbabwe",
}

CITY_TOKENS = {
    "Amsterdam", "Athens", "Atlanta", "Auckland", "Baghdad", "Bangkok",
    "Barcelona", "Beijing", "Berlin", "Bogota", "Brussels", "Budapest",
    "Buenos", "Cairo", "Casablanca", "Chicago", "Colombo", "Copenhagen",
    "Dallas", "Delhi", "Denver", "Detroit", "Dubai", "Dublin", "Edinburgh",
    "Frankfurt", "Geneva", "Hamburg", "Hanoi", "Helsinki", "Houston",
    "Istanbul", "Jakarta", "Johannesburg", "Karachi", "Kiev", "Kyiv",
    "Lagos", "Lahore", "Lima", "Lisbon", "London", "Angeles", "Francisco",
    "Luanda", "Madrid", "Manila", "Melbourne", "Mexico", "Miami", "Milan",
    "Minsk", "Montreal", "Moscow", "Mumbai", "Munich", "Nairobi",
    "Osaka", "Oslo", "Paris", "Prague", "Riyadh", "Rome", "Seoul",
    "Shanghai", "Sofia", "Stockholm", "Sydney", "Taipei", "Tehran",
    "Tokyo", "Toronto", "Vancouver", "Vienna", "Warsaw", "Washington",
    "Zurich", "York",  # "New York"
}

CRYPTO_TOKENS = {
    "Bitcoin", "Ethereum", "Litecoin", "Ripple", "Dogecoin", "Cardano",
    "Solana", "Polkadot", "Chainlink", "Tether", "Binance", "Avalanche",
    "Polygon", "Uniswap", "Stellar", "Monero", "Tron", "Cosmos",
    "Algorand", "Filecoin",
}

COMPANY_TOKENS = {
    "Apple", "Google", "Microsoft", "Amazon", "Facebook", "Netflix",
    "Twitter", "Tesla", "Samsung", "Nvidia", "Intel", "Adobe", "Uber",
    "Lyft", "Airbnb", "Spotify", "Walmart", "Nike", "Adidas", "Disney",
    "Sony", "Panasonic", "Toyota", "Honda", "Ford", "Ferrari", "Porsche",
    "BMW", "Mercedes", "Volkswagen", "Audi", "Rivian", "Instagram",
    "LinkedIn", "TikTok", "Snapchat", "Pinterest", "Reddit", "Discord",
    "Slack", "Zoom", "Salesforce", "Oracle", "IBM", "Cisco", "Qualcomm",
    "Huawei", "Xiaomi", "Alibaba", "Tencent", "Baidu",
}

PERSON_NAME_TOKENS = {
    "Doe",
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Miller",
    "Davis",
    "Garcia",
    "Wilson",
    "Moore",
    "Taylor",
    "Anderson",
    "Thomas",
    "Jackson",
    "White",
    "Harris",
    "Martin",
    "Thompson",
    "Lee",
    "Kim",
    "Chen",
    "Wang",
    "Zhang",
    "Liu",
}

GEO_NAME_TOKENS = {
    "Paris",
    "London",
    "Tokyo",
    "Berlin",
    "Munich",
    "Osaka",
    "Chicago",
    "York",
    "Angeles",
    "Francisco",
    "China",
    "Japan",
    "India",
    "Korea",
    "States",
    "Kingdom",
    "America",
    "Europe",
    "Asia",
}


def extract_entities(text: str) -> List[str]:
    found = []
    seen = set()

    for pattern in (ENTITY_RE, CODE_RE, ACRONYM_RE):
        for match in pattern.finditer(text):
            entity = match.group(0).strip("-")
            if entity in STOP_ENTITIES or entity in seen:
                continue
            if len(entity) < 2:
                continue
            seen.add(entity)
            found.append(entity)

    return found


# Tokens that signal a multi-word entity is a country name
COUNTRY_PART_TOKENS = {
    "States", "Kingdom", "Emirates", "Republic", "Arabia", "Union",
    "Federation", "Islands", "Africa", "Zealand", "Korea",
}


def bucket_entity(entity: str) -> str:
    if entity in STOP_ENTITIES:
        return "stop"
    if CODE_RE.fullmatch(entity):
        return "code"
    if ACRONYM_RE.fullmatch(entity):
        if len(entity) < 3:
            return "stop"
        return "acronym"
    if " " in entity or "-" in entity:
        parts = re.split(r"[\s-]+", entity)
        if any(part in PERSON_NAME_TOKENS for part in parts):
            return "multi_word_person"
        # Distinguish multi-word countries from multi-word cities.
        # Limit to ≤2 tokens: 3+ token entities (e.g. "Los Angeles Lakers") are
        # likely sports teams or organisations, not bare place names.
        if any(part in COUNTRY_TOKENS | COUNTRY_PART_TOKENS for part in parts):
            return "multi_word_country" if len(parts) <= 2 else "multi_word_other"
        if any(part in CITY_TOKENS for part in parts):
            return "multi_word_city" if len(parts) <= 2 else "multi_word_other"
        if any(part in GEO_NAME_TOKENS for part in parts):
            return "multi_word_geo"
        return "multi_word_other"
    if len(entity) < 4:
        return "stop"
    # Fine-grained single-token buckets — keeps semantically incompatible
    # entities (country / city / crypto / company) in separate groups
    # so they never get auto-paired with each other.
    if entity in CRYPTO_TOKENS:
        return "crypto"
    if entity in COMPANY_TOKENS:
        return "company"
    if entity in COUNTRY_TOKENS:
        return "country"
    if entity in CITY_TOKENS:
        return "city"
    if entity in GEO_NAME_TOKENS:
        return "geo"
    return "single_word"


def collect_entity_stats(examples: Iterable[Dict]) -> Dict[str, Dict[str, int]]:
    stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"output_freq": 0, "context_freq": 0, "both_freq": 0, "examples": 0}
    )

    for example in examples:
        output = example.get("output", "")
        context = example.get("context", "")
        output_entities = set(extract_entities(output))
        context_entities = set(extract_entities(context))
        shared = output_entities & context_entities

        for entity in output_entities:
            stats[entity]["output_freq"] += 1
        for entity in context_entities:
            stats[entity]["context_freq"] += 1
        for entity in shared:
            stats[entity]["both_freq"] += 1
            stats[entity]["examples"] += 1

    return dict(stats)


def suggest_replacement_pairs(
    stats: Dict[str, Dict[str, int]],
    min_both_freq: int = 2,
) -> Tuple[Dict[str, str], List[Dict]]:
    corruptible = [
        entity
        for entity, row in stats.items()
        if row["both_freq"] >= min_both_freq
    ]

    buckets: Dict[str, List[str]] = defaultdict(list)
    for entity in corruptible:
        bucket = bucket_entity(entity)
        if bucket == "stop":
            continue
        buckets[bucket].append(entity)

    for bucket_name in buckets:
        buckets[bucket_name].sort(
            key=lambda e: (stats[e]["both_freq"], stats[e]["output_freq"]),
            reverse=True,
        )

    # Seed from the hand-curated dict — auto-collected pairs only fill gaps.
    replacements: Dict[str, str] = dict(CURATED_REPLACEMENTS)
    pair_records: List[Dict] = []

    for bucket_name, entities in buckets.items():
        for i in range(0, len(entities) - 1, 2):
            left, right = entities[i], entities[i + 1]
            if left == right:
                continue
            # Reject pairs where one name is a substring of the other
            if left.lower() in right.lower() or right.lower() in left.lower():
                continue
            # Reject pairs that share a significant token (avoids city ↔ country in geo)
            left_tokens = set(re.split(r"[\s\-]+", left.lower()))
            right_tokens = set(re.split(r"[\s\-]+", right.lower()))
            if left_tokens & right_tokens:
                continue
            # Skip if the curated dict already covers either entity
            if left in replacements or right in replacements:
                continue
            replacements[left] = right
            replacements[right] = left
            pair_records.append(
                {
                    "from": left,
                    "to": right,
                    "bucket": bucket_name,
                    "left_both_freq": stats[left]["both_freq"],
                    "right_both_freq": stats[right]["both_freq"],
                }
            )

    return replacements, pair_records


def build_entity_report(
    examples: List[Dict],
    min_both_freq: int = 2,
    top_k: int = 100,
) -> Dict:
    stats = collect_entity_stats(examples)
    replacements, pair_records = suggest_replacement_pairs(stats, min_both_freq=min_both_freq)

    ranked = sorted(
        stats.items(),
        key=lambda item: (item[1]["both_freq"], item[1]["output_freq"]),
        reverse=True,
    )

    return {
        "summary": {
            "num_examples": len(examples),
            "unique_entities": len(stats),
            "corruptible_entities": sum(
                1 for _, row in stats.items() if row["both_freq"] >= min_both_freq
            ),
            "replacement_pairs": len(pair_records),
        },
        "top_entities": [
            {
                "entity": entity,
                **row,
                "bucket": bucket_entity(entity),
                "has_replacement": entity in replacements,
                "replacement": replacements.get(entity),
            }
            for entity, row in ranked[:top_k]
        ],
        "replacement_pairs": pair_records,
        "replacements": replacements,
        "stats": stats,
    }


def save_entity_report(report: Dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    replacements_path = out_dir / "entity_replacements.json"
    candidates_path = out_dir / "entity_candidates.json"
    pairs_path = out_dir / "entity_replacement_pairs.json"

    with replacements_path.open("w", encoding="utf-8") as f:
        json.dump(report["replacements"], f, ensure_ascii=False, indent=2)

    candidates = {
        "summary": report["summary"],
        "top_entities": report["top_entities"],
    }
    with candidates_path.open("w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)

    with pairs_path.open("w", encoding="utf-8") as f:
        json.dump(report["replacement_pairs"], f, ensure_ascii=False, indent=2)

    print(f"Saved replacements: {replacements_path} ({len(report['replacements'])} entries)")
    print(f"Saved candidates:     {candidates_path}")
    print(f"Saved pair list:      {pairs_path}")


def load_entity_replacements(path: Path | None = None) -> Dict[str, str]:
    path = path or DEFAULT_ENTITY_REPLACEMENTS_PATH
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict in {path}")
    return data
