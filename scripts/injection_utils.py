"""Utilities for injecting synthetic hallucinations into tool-calling examples."""

from __future__ import annotations

import copy
import json
import os
import random
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ConflictCandidate = Tuple[int, int, str, str, str]  # start, end, replacement, label_type, corruption_type


# Commas only allowed as proper thousands separators (must be followed by exactly 3 digits).
# This prevents matching list-context numbers like "0," or "1," in "[0, 1, 2]".
NUM_RE = re.compile(r"(?<![\w])[$€£]?[+-]?\d\d*(?:,\d{3})*(?:\.\d+)?%?(?![\w])")

ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
US_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
MONTH_DATE_RE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:[\s-][A-Z][a-z]+){0,3}\b")

MONTH_TO_NUM = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
NUM_TO_MONTH = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

STOP_ENTITIES = {
    "The",
    "This",
    "That",
    "These",
    "Those",
    "If",
    "When",
    "Where",
    "What",
    "Which",
    "Who",
    "How",
    "Yes",
    "No",
    "Here",
    "There",
    "Please",
    "Thank",
    "Thanks",
    "Hello",
    "Hi",
    "Feel",
    "Free",
    "Based",
    "According",
    "However",
    "Additionally",
    "Also",
    "For",
    "With",
    "From",
    "Your",
    "You",
    "Assistant",
    "User",
    "Tool",
    "API",
    "Status",
    "Success",
    "Error",
    "Details",
    "Results",
    "Report",
    "Validation",
    "Order",
    "Number",
    # Generic nouns that appear title-cased in tool outputs
    "Team", "Player", "User", "Male", "Female", "Session", "Image",
    "Sport", "Rating", "Match", "Movie", "Product", "Tier", "Formula",
    "Comment", "Mortgage", "Item", "Value", "Entry", "Record", "Category",
    "Model", "Version", "Build", "Release", "Service", "Source", "Target",
    "Member", "Profile", "Account", "Message", "Thread", "Channel",
    "Review", "Score", "Rank", "Level", "Stage", "Round", "Phase",
    "Role", "Type", "Mode", "Tag", "Label", "Class", "Group",
    "Name", "Code", "Live",
}

WORD_REPLACEMENTS = {
    "sunny": "rainy",
    "rainy": "sunny",
    "cloudy": "sunny",
    "clear": "stormy",
    "stormy": "clear",
    "available": "unavailable",
    "unavailable": "available",
    "open": "closed",
    "closed": "open",
    "active": "inactive",
    "inactive": "active",
    "approved": "rejected",
    "rejected": "approved",
    "success": "failure",
    "successful": "unsuccessful",
    "failed": "passed",
    "passed": "failed",
    "valid": "invalid",
    "invalid": "valid",
    "true": "false",
    "false": "true",
    "yes": "no",
    "no": "yes",
    "enabled": "disabled",
    "disabled": "enabled",
    "online": "offline",
    "offline": "online",
    "completed": "cancelled",
    "cancelled": "completed",
    "confirmed": "denied",
    "denied": "confirmed",
    "pending": "resolved",
    "resolved": "pending",
    "public": "private",
    "private": "public",
    "high": "low",
    "low": "high",
    "increase": "decrease",
    "decrease": "increase",
    "positive": "negative",
    "negative": "positive",
    "win": "loss",
    "loss": "win",
    "free": "paid",
    "paid": "free",
    "connected": "disconnected",
    "disconnected": "connected",
    "scheduled": "cancelled",
    "running": "stopped",
    "stopped": "running",
    "healthy": "unhealthy",
    "unhealthy": "healthy",
    "stable": "volatile",
    "volatile": "stable",
    "eligible": "ineligible",
    "ineligible": "eligible",
}

DEFAULT_ENTITY_REPLACEMENTS_PATH = Path("data/interim/entity_replacements.json")
_MERGED_ENTITY_REPLACEMENTS: Optional[Dict[str, str]] = None

ENTITY_REPLACEMENTS = {
    # Cities
    "Paris": "London",
    "London": "Paris",
    "Berlin": "Munich",
    "Munich": "Berlin",
    "Tokyo": "Osaka",
    "Osaka": "Tokyo",
    "New York": "Chicago",
    "Chicago": "New York",
    "Los Angeles": "San Francisco",
    "San Francisco": "Los Angeles",
    "Sydney": "Melbourne",
    "Melbourne": "Sydney",
    "Toronto": "Vancouver",
    "Vancouver": "Toronto",
    "Shanghai": "Beijing",
    "Beijing": "Shanghai",
    "Dubai": "Abu Dhabi",
    "Abu Dhabi": "Dubai",
    "Madrid": "Barcelona",
    "Barcelona": "Madrid",
    "Rome": "Milan",
    "Milan": "Rome",
    "Amsterdam": "Rotterdam",
    "Rotterdam": "Amsterdam",
    "Vienna": "Zurich",
    "Zurich": "Vienna",
    "Seoul": "Busan",
    "Busan": "Seoul",
    "Singapore": "Kuala Lumpur",
    "Kuala Lumpur": "Singapore",
    # Countries
    "Canada": "Mexico",
    "Mexico": "Canada",
    "India": "China",
    "China": "India",
    "France": "Germany",
    "Germany": "France",
    "Japan": "South Korea",
    "South Korea": "Japan",
    "Australia": "New Zealand",
    "New Zealand": "Australia",
    "Brazil": "Argentina",
    "Argentina": "Brazil",
    "United States": "United Kingdom",
    "United Kingdom": "United States",
    "Italy": "Spain",
    "Spain": "Italy",
    "Russia": "Ukraine",
    "Ukraine": "Russia",
    "Netherlands": "Belgium",
    "Belgium": "Netherlands",
    "Sweden": "Norway",
    "Norway": "Sweden",
    "Poland": "Czech Republic",
    "Czech Republic": "Poland",
    "Portugal": "Greece",
    "Greece": "Portugal",
    "Switzerland": "Austria",
    "Austria": "Switzerland",
    # Person first names
    "John": "James",
    "James": "John",
    "Jane": "Sarah",
    "Sarah": "Jane",
    "Michael": "Robert",
    "Robert": "Michael",
    "David": "Daniel",
    "Daniel": "David",
    "Emily": "Emma",
    "Emma": "Emily",
    "Chris": "Mark",
    "Mark": "Chris",
    "Paul": "Peter",
    "Peter": "Paul",
    "Tom": "Tim",
    "Tim": "Tom",
    "Lisa": "Laura",
    "Laura": "Lisa",
    "Anna": "Alice",
    "Alice": "Anna",
    "Mary": "Susan",
    "Susan": "Mary",
    "Kevin": "Brian",
    "Brian": "Kevin",
    "Eric": "Ryan",
    "Ryan": "Eric",
    "Amy": "Kate",
    "Kate": "Amy",
    "Alex": "Adam",
    "Adam": "Alex",
    "Jessica": "Jennifer",
    "Jennifer": "Jessica",
    "William": "Thomas",
    "Thomas": "William",
    "George": "Henry",
    "Henry": "George",
    "Patrick": "Nathan",
    "Nathan": "Patrick",
    # Person last names
    "Smith": "Johnson",
    "Johnson": "Smith",
    "Brown": "Wilson",
    "Wilson": "Brown",
    "Jones": "Davis",
    "Davis": "Jones",
    "Miller": "Taylor",
    "Taylor": "Miller",
    "Anderson": "Thompson",
    "Thompson": "Anderson",
    "White": "Harris",
    "Harris": "White",
    "Martin": "Garcia",
    "Garcia": "Martin",
    "Martinez": "Rodriguez",
    "Rodriguez": "Martinez",
    "Lee": "Kim",
    "Kim": "Lee",
    "Walker": "Hall",
    "Hall": "Walker",
    "Doe": "Smith",
    "Mack": "Moore",
    "Moore": "Mack",
    # Cars / brands
    "Ferrari": "Porsche",
    "Porsche": "Ferrari",
    "BMW": "Mercedes",
    "Mercedes": "BMW",
    "Toyota": "Honda",
    "Honda": "Toyota",
    "Ford": "Chevrolet",
    "Chevrolet": "Ford",
    "Volkswagen": "Audi",
    "Audi": "Volkswagen",
    # Tech companies
    "Apple": "Samsung",
    "Samsung": "Apple",
    "Google": "Microsoft",
    "Microsoft": "Google",
    "Amazon": "Walmart",
    "Walmart": "Amazon",
    "Tesla": "Rivian",
    "Rivian": "Tesla",
    "Netflix": "Hulu",
    "Hulu": "Netflix",
    "Spotify": "Apple Music",
    "Apple Music": "Spotify",
    "Twitter": "LinkedIn",
    "LinkedIn": "Twitter",
    "Facebook": "Instagram",
    "Instagram": "Facebook",
    "Uber": "Lyft",
    "Lyft": "Uber",
    # Cryptocurrencies
    "Bitcoin": "Ethereum",
    "Ethereum": "Bitcoin",
    "Litecoin": "Dogecoin",
    "Dogecoin": "Litecoin",
    # Historical / fictional names
    "King Arthur": "King Richard",
    "King Richard": "King Arthur",
    "Buster Keaton": "Charlie Chaplin",
    "Charlie Chaplin": "Buster Keaton",
    "Mars": "Jupiter",
    "Jupiter": "Mars",
    # Genomics / science
    "BRCA1": "BRCA2",
    "BRCA2": "BRCA1",
    "AlphaFold": "RoseTTAFold",
    "RoseTTAFold": "AlphaFold",
    # Languages
    "English": "French",
    "French": "English",
    "Spanish": "Portuguese",
    "Portuguese": "Spanish",
    "German": "Dutch",
    "Dutch": "German",
    # Genres / categories
    "Fantasy": "Horror",
    "Horror": "Fantasy",
    "Romance": "Thriller",
    "Thriller": "Romance",
    "Action": "Drama",
    "Drama": "Action",
    "Comedy": "Mystery",
    "Mystery": "Comedy",
    # Reference sites
    "WikiHow": "Instructables",
    "Instructables": "WikiHow",
    "Wikipedia": "Britannica",
    "Britannica": "Wikipedia",
    # More cities
    "Miami": "Houston",
    "Houston": "Miami",
    "Seattle": "Portland",
    "Portland": "Seattle",
    "Denver": "Phoenix",
    "Phoenix": "Denver",
    "Dallas": "Austin",
    "Austin": "Dallas",
    "Atlanta": "Nashville",
    "Nashville": "Atlanta",
    "Boston": "Philadelphia",
    "Philadelphia": "Boston",
    "Detroit": "Cleveland",
    "Cleveland": "Detroit",
    "Minneapolis": "Milwaukee",
    "Milwaukee": "Minneapolis",
    "Stockholm": "Copenhagen",
    "Copenhagen": "Stockholm",
    "Brussels": "Zurich",
    "Lisbon": "Athens",
    "Athens": "Lisbon",
    "Warsaw": "Prague",
    "Prague": "Warsaw",
    "Budapest": "Bucharest",
    "Bucharest": "Budapest",
    "Mumbai": "Delhi",
    "Delhi": "Mumbai",
    "Bangalore": "Chennai",
    "Chennai": "Bangalore",
    "Lagos": "Nairobi",
    "Nairobi": "Lagos",
    "Cairo": "Casablanca",
    "Casablanca": "Cairo",
    # NBA teams
    "Los Angeles Lakers": "Brooklyn Nets",
    "Brooklyn Nets": "Los Angeles Lakers",
    "Golden State Warriors": "Boston Celtics",
    "Boston Celtics": "Golden State Warriors",
    "Chicago Bulls": "Miami Heat",
    "Miami Heat": "Chicago Bulls",
    "Dallas Mavericks": "Phoenix Suns",
    "Phoenix Suns": "Dallas Mavericks",
    "Milwaukee Bucks": "Toronto Raptors",
    "Toronto Raptors": "Milwaukee Bucks",
    "Los Angeles Clippers": "Denver Nuggets",
    "Denver Nuggets": "Los Angeles Clippers",
    # NFL teams
    "Dallas Cowboys": "New England Patriots",
    "New England Patriots": "Dallas Cowboys",
    "Kansas City Chiefs": "Philadelphia Eagles",
    "Philadelphia Eagles": "Kansas City Chiefs",
    "San Francisco 49ers": "Seattle Seahawks",
    "Seattle Seahawks": "San Francisco 49ers",
    # MLB teams
    "New York Yankees": "Boston Red Sox",
    "Boston Red Sox": "New York Yankees",
    "New York Mets": "Chicago Cubs",
    "Chicago Cubs": "New York Mets",
    "Los Angeles Dodgers": "San Francisco Giants",
    "San Francisco Giants": "Los Angeles Dodgers",
    # Soccer clubs
    "Real Madrid": "Barcelona",
    "Manchester United": "Liverpool",
    "Liverpool": "Manchester United",
    "Bayern Munich": "Borussia Dortmund",
    "Borussia Dortmund": "Bayern Munich",
    "Paris Saint-Germain": "Lyon",
    "Lyon": "Paris Saint-Germain",
    "Juventus": "Inter Milan",
    "Inter Milan": "Juventus",
    "Arsenal": "Chelsea",
    "Chelsea": "Arsenal",
    "Tottenham": "Leicester",
    "Leicester": "Tottenham",
    # More programming languages
    "Python": "JavaScript",
    "JavaScript": "Python",
    "TypeScript": "Kotlin",
    "Kotlin": "TypeScript",
    "Java": "Swift",
    "Swift": "Java",
    "Rust": "Go",
    "Go": "Rust",
    "Ruby": "Perl",
    "Perl": "Ruby",
    "Scala": "Haskell",
    "Haskell": "Scala",
    "PHP": "Ruby",
    "Dart": "TypeScript",
    # Databases / cloud
    "PostgreSQL": "MySQL",
    "MySQL": "PostgreSQL",
    "MongoDB": "Cassandra",
    "Cassandra": "MongoDB",
    "Redis": "Memcached",
    "Memcached": "Redis",
    "AWS": "Azure",
    "Azure": "AWS",
    "Kubernetes": "Docker",
    "Docker": "Kubernetes",
}

OVERGENERATION_CLAUSES_BY_DOMAIN = {
    "weather": [
        "the weather has been fairly good over the past few months",
        "conditions have stayed mostly consistent in recent weeks",
        "this kind of pattern is typical for the current season",
    ],
    "price|cost|stock|market|rate": [
        "prices in this range have moved steadily over the last quarter",
        "similar offerings have been trending slightly higher recently",
        "this level is above the recent monthly average",
    ],
    "health|medical|symptom|patient": [
        "recovery timelines for similar cases are usually a few weeks longer",
        "follow-up observations often show gradual improvement after this stage",
    ],
    "travel|flight|hotel|route": [
        "demand for this route has remained strong throughout the season",
        "availability has been tighter than usual on comparable dates",
    ],
    "game|event|battle|alliance|character": [
        "these events are often cited as turning points in later storylines",
        "players usually encounter related consequences in subsequent missions",
    ],
    "report|validation|status|order|result": [
        "similar reviews in this category rarely surface major issues afterward",
        "outcomes like this typically remain stable in follow-up checks",
    ],
    "default": [
        "this pattern has remained fairly consistent over the past few months",
        "similar cases have usually stayed within the same range recently",
        "this kind of result is often seen in comparable situations",
    ],
}

CLOSING_SENTENCE_RE = re.compile(
    r"(feel free to ask|let me know if|if you need (any )?(more|further|additional)|"
    r"don't hesitate|happy to help|glad to help|if you have any questions|"
    r"please let me know|i hope this helps)",
    re.IGNORECASE,
)

OVERGENERATION_META_LABEL_RE = re.compile(
    r"^(?:good clause|bad clause|overgeneration)\s*:\s*(.+)$",
    re.IGNORECASE,
)

OVERGENERATION_LEADING_BOILERPLATE_RE = re.compile(
    r"^(?:sure thing|sure|certainly!?|based on the|here'?s|okay|ok|i will|let'?s|"
    r"good choice|great insight provided)\s*[,:-]?\s*",
    re.IGNORECASE,
)

OVERGENERATION_INVALID_CHECKS = [
    ("missing_tool", re.compile(
        r"would you like|should i|shall i|book a|purchase|subscribe|place an order|"
        r"send (this|it) to your email|one-click purchase",
        re.IGNORECASE,
    )),
    ("question", re.compile(r"\?\s*$|^(can you|could you|would you|do you|should we)\b", re.IGNORECASE)),
    ("tool_mention", re.compile(
        r"\b(tool|api)\b|returned from the tool|the tool does|according to the tool|from the tool",
        re.IGNORECASE,
    )),
    ("list_dump", re.compile(r":\s*.+(?:,\s*.+){2,}|(?:\(ID:|ID:\s*\d)", re.IGNORECASE)),
    ("assistant_voice", re.compile(
        r"^(sure,? here are|here are some|have these|i've found|you can try|let me know|"
        r"you should consider|drivers \w+)",
        re.IGNORECASE,
    )),
    ("quoted_dump", re.compile(r'["`].+["`]|\bincluding "')),
]

OVERGENERATION_MIN_WORDS = 4
OVERGENERATION_MAX_WORDS = 18

OVERGENERATION_DOMAIN_KEYWORDS = {
    "weather": ["weather", "temperature", "forecast", "rain", "sunny", "cloud"],
    "price|cost|stock|market|rate": ["price", "cost", "stock", "market", "rate", "fee", "salary"],
    "health|medical|symptom|patient": ["health", "medical", "symptom", "patient", "diagnosis", "disease"],
    "travel|flight|hotel|route": ["flight", "hotel", "travel", "route", "airport", "booking"],
    "game|event|battle|alliance|character": ["game", "battle", "alliance", "character", "quest", "lore"],
    "report|validation|status|order": ["report", "validation", "validated", "audit", "order number"],
}

MISSING_TOOL_SENTENCES = [
    "Would you like me to book a flight for you based on this information?",
    "Would you like me to purchase this item for you now?",
    "Would you like me to send this information to your email?",
    "Would you like me to schedule a meeting about this?",
    "Would you like me to reserve a hotel for you?",
    "Would you like me to place an order using your account?",
]


def read_jsonl(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_label(start: int, end: int, text: str, label_type: str) -> Dict:
    return {
        "start": start,
        "end": end,
        "text": text,
        "label_type": label_type,
    }


def validate_spans(example: Dict) -> None:
    output = example["output"]
    for label in example.get("hallucination_labels", []):
        start = label["start"]
        end = label["end"]
        text = label["text"]
        actual = output[start:end]
        if actual != text:
            raise ValueError(
                f"Span mismatch in {example.get('id')}: expected {text!r}, got {actual!r}"
            )


def _extract_prefix_suffix(value: str) -> Tuple[str, str, str]:
    prefix = ""
    suffix = ""
    core = value

    if core and core[0] in "$€£":
        prefix = core[0]
        core = core[1:]

    if core.endswith("%"):
        suffix = "%"
        core = core[:-1]

    return prefix, suffix, core


def _format_number(prefix: str, suffix: str, number: float, original: str) -> str:
    if suffix == "%":
        sign = "+" if number >= 0 else ""
        return f"{sign}{number:.2f}%"

    if "." in original.replace(",", ""):
        decimals = len(original.split(".")[-1].replace("%", ""))
        decimals = min(max(decimals, 2), 4)
        formatted = f"{number:,.{decimals}f}" if "," in original else f"{number:.{decimals}f}"
        return prefix + formatted

    return prefix + str(int(round(number)))


def corrupt_number(value: str, strategy: Optional[str] = None) -> str:
    """Apply one of several numeric corruption strategies."""
    prefix, suffix, core = _extract_prefix_suffix(value)

    if suffix == "%":
        strategies = ["percent_flip", "multiply_150", "add_points", "sign_flip"]
    elif "." in core:
        strategies = ["multiply_150", "divide_2", "add_fixed", "scale_10"]
    else:
        strategies = ["multiply_150", "divide_2", "add_fixed", "scale_10", "digit_swap"]

    strategy = strategy or random.choice(strategies)
    normalized = core.replace(",", "")

    try:
        number = float(normalized.replace("+", ""))
    except ValueError:
        return prefix + "9999"

    if strategy == "percent_flip":
        if normalized.startswith("+"):
            return "-9.99%"
        if normalized.startswith("-"):
            return "+9.99%"
        return "150.00%"

    if strategy == "multiply_150":
        return _format_number(prefix, suffix, number * 1.5, value)

    if strategy == "divide_2":
        new_number = number / 2 if number else 1
        return _format_number(prefix, suffix, new_number, value)

    if strategy == "add_fixed":
        delta = 111.11 if "." in normalized else 101
        return _format_number(prefix, suffix, number + delta, value)

    if strategy == "add_points":
        return _format_number(prefix, suffix, number + random.choice([5.5, 9.99, 12.5]), value)

    if strategy == "sign_flip":
        return _format_number(prefix, suffix, -number if number else -1, value)

    if strategy == "scale_10":
        factor = 10 if abs(number) < 1000 else 0.1
        return _format_number(prefix, suffix, number * factor, value)

    if strategy == "digit_swap" and len(normalized.replace("+", "").replace("-", "")) >= 2:
        digits = list(normalized.replace("+", "").replace("-", ""))
        digits[0], digits[1] = digits[1], digits[0]
        swapped = float("".join(digits))
        if normalized.startswith("-"):
            swapped = -swapped
        return _format_number(prefix, suffix, swapped, value)

    return _format_number(prefix, suffix, number + 101, value)


def _shift_iso_date(text: str) -> Optional[str]:
    match = ISO_DATE_RE.search(text)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    try:
        original = date(year, month, day)
    except ValueError:
        return None
    shifted = original + timedelta(days=random.choice([45, 90, 120, 180, 365]))
    return shifted.isoformat()


def _shift_us_date(text: str) -> Optional[str]:
    match = US_DATE_RE.search(text)
    if not match:
        return None
    month, day, year = map(int, match.groups())
    try:
        original = date(year, month, day)
    except ValueError:
        return None
    shifted = original + timedelta(days=random.choice([30, 60, 120, 240]))
    return f"{shifted.month}/{shifted.day}/{shifted.year}"


def _shift_month_date(text: str) -> Optional[str]:
    match = MONTH_DATE_RE.search(text)
    if not match:
        return None
    month_name, day, year = match.groups()
    month = MONTH_TO_NUM[month_name.lower()]
    try:
        original = date(int(year), month, int(day))
    except ValueError:
        return None
    shifted = original + timedelta(days=random.choice([45, 120, 200]))
    return f"{NUM_TO_MONTH[shifted.month]} {shifted.day}, {shifted.year}"


def _shift_year(text: str) -> Optional[str]:
    match = YEAR_RE.search(text)
    if not match:
        return None
    year = int(match.group(1))
    return str(year + random.choice([-2, -1, 1, 2, 3]))


def corrupt_date(value: str) -> Optional[str]:
    for shifter in (_shift_iso_date, _shift_us_date, _shift_month_date, _shift_year):
        replacement = shifter(value)
        if replacement and replacement != value:
            return replacement
    return None


def _is_inside_date_span(text: str, start: int, end: int) -> bool:
    """Skip numeric tokens that belong to a larger date expression."""
    date_patterns = [ISO_DATE_RE, US_DATE_RE, MONTH_DATE_RE]
    for pattern in date_patterns:
        for date_match in pattern.finditer(text):
            if start >= date_match.start() and end <= date_match.end():
                return True
    return False


def find_numeric_conflict(output: str, context: str) -> Optional[ConflictCandidate]:
    for match in NUM_RE.finditer(output):
        original = match.group(0)
        if len(original) < 2:
            continue
        if _is_inside_date_span(output, match.start(), match.end()):
            continue
        if original not in context:
            continue
        replacement = corrupt_number(original)
        if replacement != original:
            return match.start(), match.end(), replacement, "Evident Conflict", "number"
    return None


def find_date_conflict(output: str, context: str) -> Optional[ConflictCandidate]:
    patterns = [ISO_DATE_RE, US_DATE_RE, MONTH_DATE_RE, YEAR_RE]
    for pattern in patterns:
        for match in pattern.finditer(output):
            original = match.group(0)
            if original not in context:
                continue
            replacement = corrupt_date(original)
            if replacement and replacement != original:
                return match.start(), match.end(), replacement, "Evident Conflict", "date"
    return None


def get_entity_replacements(extra_path: Optional[Path] = None) -> Dict[str, str]:
    """Return the curated built-in dict, optionally merged with a user-supplied file.

    The auto-collected entity_replacements.json is NOT loaded automatically because
    co-occurrence-based pairs can be nonsensical (e.g. "Jazz" -> "Hopefully").
    Pass extra_path explicitly (via --entity-replacements) only after reviewing the file.
    Built-in entries always take priority over extra_path entries.
    """
    global _MERGED_ENTITY_REPLACEMENTS

    if extra_path is None:
        if _MERGED_ENTITY_REPLACEMENTS is None:
            _MERGED_ENTITY_REPLACEMENTS = dict(ENTITY_REPLACEMENTS)
        return _MERGED_ENTITY_REPLACEMENTS

    # User explicitly passed a file — merge it, but built-in still wins.
    merged: Dict[str, str] = {}
    if extra_path.exists():
        with extra_path.open("r", encoding="utf-8") as f:
            auto_map = json.load(f)
        if isinstance(auto_map, dict):
            merged.update(auto_map)
    merged.update(ENTITY_REPLACEMENTS)
    return merged


def _replacement_for_entity(entity: str) -> Optional[str]:
    replacements = get_entity_replacements()
    if entity in replacements:
        return replacements[entity]

    lower_map = {k.lower(): v for k, v in replacements.items()}
    if entity.lower() in lower_map:
        replacement = lower_map[entity.lower()]
        if entity.isupper():
            return replacement.upper()
        if entity[0].isupper():
            return replacement[0].upper() + replacement[1:]
        return replacement
    return None


def find_entity_conflict(output: str, context: str) -> Optional[ConflictCandidate]:
    seen = set()
    for match in ENTITY_RE.finditer(output):
        entity = match.group(0)
        if entity in seen or entity in STOP_ENTITIES:
            continue
        seen.add(entity)
        if entity not in context:
            continue
        replacement = _replacement_for_entity(entity)
        if not replacement or replacement == entity:
            continue
        return match.start(), match.end(), replacement, "Evident Conflict", "entity"
    return None


# Only match numbers NOT immediately preceded by a letter, so we skip identifier suffixes
# like "filter1", "post1", "Female1" while still catching "project_123", "sess-67890".
_NUMBER_IN_STRING_RE = re.compile(r"(?<![a-zA-Z])\d+")

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

# Values so generic they're not worth corrupting as standalone strings
_BORING_VALUES = {
    "true", "false", "null", "none", "n/a", "na", "yes", "no",
    "success", "error", "ok", "okay", "pending", "done",
}


def _corrupt_embedded_number(s: str) -> Optional[str]:
    """Corrupt the first number embedded inside a string value (e.g. 'Soul123' → 'Soul456')."""
    m = _NUMBER_IN_STRING_RE.search(s)
    if not m:
        return None
    # Skip hex literals: "0" followed by "x/X" (e.g. "0x9ABCDEF")
    if m.group(0) == "0" and m.end() < len(s) and s[m.end()].lower() == "x":
        return None
    orig = m.group(0)
    corrupted = corrupt_number(orig)
    if corrupted == orig:
        return None
    return s[: m.start()] + corrupted + s[m.end() :]


def find_context_value_conflict(output: str, context: str) -> Optional[ConflictCandidate]:
    """Parse context as JSON, find leaf string values appearing verbatim in output, corrupt them.

    This catches proper names, identifiers, and other string values from the tool JSON
    that the numeric/date/entity finders would miss because they rely on token-level regex.
    """
    try:
        data = json.loads(context)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None

    string_leaves: List[str] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, str) and 2 <= len(obj) <= 120:
            string_leaves.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)

    # Prefer longer, more specific values; shuffle within each length bucket for variety
    string_leaves = [v for v in string_leaves if v.lower() not in _BORING_VALUES]
    # Skip URLs and data URIs (base64 blobs, http links, etc.)
    string_leaves = [v for v in string_leaves if not _URL_RE.match(v)]
    string_leaves = [v for v in string_leaves if not v.startswith("data:")]
    # Skip code/template strings containing angle-bracket placeholders, hex prefixes, etc.
    string_leaves = [v for v in string_leaves if not re.search(r"<[^>]+>|\[\.\.\.?\]|0x[0-9A-Fa-f]", v)]
    # Sort descending by length so we prefer specific matches over single words
    string_leaves.sort(key=lambda v: len(v), reverse=True)
    # Randomise within same-length groups to vary corruption type across runs
    random.shuffle(string_leaves)

    for value in string_leaves:
        idx = output.find(value)
        if idx == -1:
            continue
        end = idx + len(value)

        # 1. Entity replacement (dict lookup)
        replacement = _replacement_for_entity(value)
        if replacement and replacement != value:
            return (idx, end, replacement, "Evident Conflict", "entity")

        # 2. Corrupt an embedded number within the string (e.g. IDs, usernames, codes)
        corrupted = _corrupt_embedded_number(value)
        if corrupted and corrupted != value:
            return (idx, end, corrupted, "Evident Conflict", "number")

    return None


def find_word_conflict(output: str, context: str) -> Optional[ConflictCandidate]:
    context_lower = context.lower()
    matches: List[ConflictCandidate] = []
    items = list(WORD_REPLACEMENTS.items())
    random.shuffle(items)

    for original, replacement in items:
        pattern = re.compile(rf"\b{re.escape(original)}\b", re.IGNORECASE)
        for match in pattern.finditer(output):
            if original not in context_lower:
                continue
            matched = output[match.start() : match.end()]
            if matched.isupper():
                repl = replacement.upper()
            elif matched[0].isupper():
                repl = replacement.capitalize()
            else:
                repl = replacement
            matches.append(
                (match.start(), match.end(), repl, "Evident Conflict", "word")
            )

    if not matches:
        return None
    return random.choice(matches)


CONFLICT_FINDER_BY_TYPE = {
    "date": find_date_conflict,
    "entity": find_entity_conflict,
    "context_value": find_context_value_conflict,
    "number": find_numeric_conflict,
    "word": find_word_conflict,
}

CONFLICT_FINDERS: List[Callable[[str, str], Optional[ConflictCandidate]]] = [
    find_date_conflict,
    find_entity_conflict,
    find_context_value_conflict,
    find_numeric_conflict,
    find_word_conflict,
]


def find_conflict_candidates(
    output: str,
    context: str,
    corruption_types: Optional[List[str]] = None,
) -> List[ConflictCandidate]:
    if corruption_types:
        finders = [
            CONFLICT_FINDER_BY_TYPE[name]
            for name in corruption_types
            if name in CONFLICT_FINDER_BY_TYPE
        ]
    else:
        finders = CONFLICT_FINDERS

    candidates = []
    used_ranges: List[Tuple[int, int]] = []

    for finder in finders:
        result = finder(output, context)
        if result is None:
            continue
        start, end, replacement, label_type, corruption_type = result
        overlap = any(not (end <= s or start >= e) for s, e in used_ranges)
        if overlap:
            continue
        candidates.append(result)
        used_ranges.append((start, end))
    return candidates


def inject_conflict(
    example: Dict,
    max_spans: int = 1,
    corruption_types: Optional[List[str]] = None,
) -> Optional[Dict]:
    ex = copy.deepcopy(example)
    output = ex["output"]
    context = ex["context"]

    candidates = find_conflict_candidates(output, context, corruption_types=corruption_types)
    if not candidates:
        return None

    selected = candidates[:max_spans]
    new_output, labels, corruption_types_out = apply_conflicts(output, selected)

    ex["id"] = f"{example['id']}_conflict"
    ex["original_output"] = output
    ex["output"] = new_output
    ex["hallucination_type"] = "conflict"
    ex["hallucination_labels"] = labels
    ex["hallucination_labels_processed"] = {
        "evident_conflict": 1,
        "baseless_info": 0,
    }
    ex["corruption_types"] = corruption_types_out

    validate_spans(ex)
    return ex


def build_conflict_dataset(
    examples: List[Dict],
    n_target: int,
    word_target: int,
    max_conflict_spans: int = 1,
    multi_conflict_rate: float = 0.15,
) -> List[Dict]:
    """Fill conflict set hitting n_target rows.

    Pass 1 — dedicated word pass to hit word_target.
    Pass 2 — any-type pass over full pool (one example per base id).
    Pass 3 — if still short, generate a second variant per base id using a
              *different* corruption type (for examples that have multiple types
              available). Each variant gets a unique id suffix (_conflict2, _conflict3…).
    """
    conflict: List[Dict] = []
    # Maps base_id -> set of corruption types already used for that id
    used_types: dict[str, set] = {}

    pool = examples[:]
    random.shuffle(pool)

    # --- Pass 1: dedicated word pass ---
    for ex in pool:
        if sum(1 for row in conflict if "word" in row.get("corruption_types", [])) >= word_target:
            break
        bid = ex["id"]
        if "word" in used_types.get(bid, set()):
            continue
        injected = inject_conflict(ex, max_spans=1, corruption_types=["word"])
        if injected is not None:
            conflict.append(injected)
            used_types.setdefault(bid, set()).add("word")

    # --- Pass 2: any-type, one variant per base example ---
    random.shuffle(pool)
    for ex in pool:
        if len(conflict) >= n_target:
            break
        bid = ex["id"]
        if bid in used_types:
            continue
        max_spans = 2 if random.random() < multi_conflict_rate else 1
        max_spans = min(max_spans, max_conflict_spans)
        injected = inject_conflict(ex, max_spans=max_spans)
        if injected is not None:
            conflict.append(injected)
            used_types.setdefault(bid, set()).update(injected.get("corruption_types", []))

    # --- Pass 3: second variant with a different type for multi-type examples ---
    if len(conflict) < n_target:
        all_types = ["date", "entity", "number", "word"]
        random.shuffle(pool)
        variant_count: dict[str, int] = {}
        for ex in pool:
            if len(conflict) >= n_target:
                break
            bid = ex["id"]
            already_used = used_types.get(bid, set())
            if not already_used:
                continue  # not corruptible at all, skip
            remaining = [t for t in all_types if t not in already_used]
            if not remaining:
                continue
            ctype = random.choice(remaining)
            injected = inject_conflict(ex, max_spans=1, corruption_types=[ctype])
            if injected is None:
                continue
            n = variant_count.get(bid, 0) + 1
            variant_count[bid] = n
            injected["id"] = f"{bid}_v{n}_conflict"
            conflict.append(injected)
            used_types[bid].add(ctype)

    return conflict


def apply_conflicts(
    output: str,
    candidates: List[ConflictCandidate],
) -> Tuple[str, List[Dict], List[str]]:
    ordered = sorted(candidates, key=lambda x: x[0], reverse=True)
    labels = []
    corruption_types = []
    new_output = output

    for start, end, replacement, label_type, corruption_type in ordered:
        original_value = new_output[start:end]
        label = make_label(
            start=start,
            end=start + len(replacement),
            text=replacement,
            label_type=label_type,
        )
        label["original_value"] = original_value
        labels.append(label)
        corruption_types.append(corruption_type)
        new_output = new_output[:start] + replacement + new_output[end:]

    labels.sort(key=lambda x: x["start"])
    return new_output, labels, corruption_types


def append_hallucinated_sentence(
    example: Dict,
    sentence: str,
    label_type: str,
    hallucination_type: str,
) -> Dict:
    ex = copy.deepcopy(example)
    original_output = ex["output"]
    base = original_output.rstrip()
    separator = " "
    start = len(base) + len(separator)
    sentence = sentence.strip()
    new_output = base + separator + sentence
    end = start + len(sentence)

    ex["id"] = f"{example['id']}_{hallucination_type}"
    ex["original_output"] = original_output
    ex["output"] = new_output
    ex["hallucination_type"] = hallucination_type
    ex["hallucination_labels"] = [
        make_label(start=start, end=end, text=sentence, label_type=label_type)
    ]
    ex["hallucination_labels_processed"] = {
        "evident_conflict": 0,
        "baseless_info": 1,
    }

    validate_spans(ex)
    return ex


def choose_missing_tool_sentence(example: Dict) -> str:
    return random.choice(MISSING_TOOL_SENTENCES)


def detect_overgeneration_domain(example: Dict) -> str:
    text = f"{example.get('query', '')} {example.get('context', '')} {example.get('output', '')}".lower()
    for domain, keywords in OVERGENERATION_DOMAIN_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return domain
    return "default"


def choose_overgeneration_clause(example: Dict, clause: Optional[str] = None) -> str:
    if clause:
        return normalize_overgeneration_clause(clause)

    domain = detect_overgeneration_domain(example)
    candidates = list(OVERGENERATION_CLAUSES_BY_DOMAIN.get(domain, OVERGENERATION_CLAUSES_BY_DOMAIN["default"]))
    context_lower = example.get("context", "").lower()

    random.shuffle(candidates)
    for candidate in candidates:
        if candidate.lower() not in context_lower:
            return candidate

    return random.choice(OVERGENERATION_CLAUSES_BY_DOMAIN["default"])


def normalize_overgeneration_clause(text: str) -> str:
    clause = text.strip().strip("\"'`")
    clause = clause.split("\n")[0].strip()

    meta_match = OVERGENERATION_META_LABEL_RE.match(clause)
    if meta_match:
        clause = meta_match.group(1).strip()

    clause = OVERGENERATION_LEADING_BOILERPLATE_RE.sub("", clause)
    clause = re.sub(r"^(and|also|additionally)[,\s]+", "", clause, flags=re.IGNORECASE)
    clause = clause.strip(" \"'")
    clause = _pick_best_overgeneration_segment(clause)
    clause = clause.rstrip(".!?")

    if not clause:
        return random.choice(OVERGENERATION_CLAUSES_BY_DOMAIN["default"])
    if clause[0].isupper():
        clause = clause[0].lower() + clause[1:]
    return clause


def _pick_best_overgeneration_segment(clause: str) -> str:
    candidates = [clause.strip()]
    candidates.extend(part.strip() for part in clause.split(";") if part.strip())
    candidates.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", clause) if part.strip())

    scored = []
    for candidate in candidates:
        words = candidate.split()
        if len(words) < OVERGENERATION_MIN_WORDS:
            continue
        if len(words) > OVERGENERATION_MAX_WORDS:
            continue
        invalid = validate_overgeneration_clause(candidate)[0] is False
        score = (0 if invalid else 10) - abs(len(words) - 12)
        scored.append((score, len(words), candidate))

    if scored:
        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return scored[0][2]

    if clause.split():
        words = clause.split()[:OVERGENERATION_MAX_WORDS]
        return " ".join(words)
    return clause


def validate_overgeneration_clause(
    clause: str,
    example: Optional[Dict] = None,
) -> Tuple[bool, str]:
    clause = clause.strip()
    if not clause:
        return False, "empty"

    words = clause.split()
    if len(words) < OVERGENERATION_MIN_WORDS:
        return False, "too_short"
    if len(words) > OVERGENERATION_MAX_WORDS:
        return False, "too_long"

    for reason, pattern in OVERGENERATION_INVALID_CHECKS:
        if pattern.search(clause):
            return False, reason

    if OVERGENERATION_META_LABEL_RE.match(clause):
        return False, "meta_label"

    if example is not None:
        context = example.get("context", "")
        output = example.get("output", "")
        if clause_supported_by_context(clause, context):
            return False, "in_context"
        if clause.lower() in output.lower():
            return False, "in_output"
        if _clause_overlaps_context_too_much(clause, context):
            return False, "context_overlap"

    return True, "ok"


def _clause_overlaps_context_too_much(clause: str, context: str) -> bool:
    clause_words = set(re.findall(r"[a-z0-9]+", clause.lower()))
    context_words = set(re.findall(r"[a-z0-9]+", context.lower()))
    if len(clause_words) < 5:
        return False
    overlap = len(clause_words & context_words) / len(clause_words)
    return overlap > 0.85


def sanitize_overgeneration_clause(
    clause: Optional[str],
    example: Dict,
) -> Tuple[str, str]:
    if clause:
        normalized = normalize_overgeneration_clause(clause)
        is_valid, _reason = validate_overgeneration_clause(normalized, example)
        if is_valid:
            return normalized, "cache"

    fallback = choose_overgeneration_clause(example, clause=None)
    return fallback, "template"


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part for part in parts if part.strip()]


def find_extendable_sentence_span(output: str) -> Tuple[int, int, str]:
    """Pick the last substantive sentence, skipping polite closings."""
    sentences = split_sentences(output)
    if not sentences:
        return 0, len(output), output

    chosen = sentences[0]
    for sentence in reversed(sentences):
        if len(sentence) < 20:
            continue
        if CLOSING_SENTENCE_RE.search(sentence):
            continue
        chosen = sentence
        break

    start = output.find(chosen)
    if start == -1:
        return 0, len(output.rstrip()), output.rstrip()
    end = start + len(chosen)
    return start, end, chosen


def clause_supported_by_context(clause: str, context: str) -> bool:
    return clause.lower() in context.lower()


def inject_overgeneration(example: Dict, clause: Optional[str] = None) -> Dict:
    """
    Overgeneration = add information not present in tool output, woven into the answer.

    Example:
      Tool: weather=sunny
      Answer: The weather in Beijing is sunny, and the weather has been pretty good
              over the past few months. [only the clause after the connector is labeled]
    """
    ex = copy.deepcopy(example)
    original_output = ex["output"]
    context = ex.get("context", "")

    chosen_clause, clause_source = sanitize_overgeneration_clause(clause, ex)

    start, end, sentence = find_extendable_sentence_span(original_output)
    sentence = sentence.rstrip()
    if sentence and sentence[-1] in ".!?":
        body = sentence[:-1]
        end_punct = sentence[-1]
    else:
        body = sentence
        end_punct = "."

    connector = random.choice([", and ", "; additionally, "])
    extended_sentence = body + connector + chosen_clause + end_punct
    new_output = original_output[:start] + extended_sentence + original_output[end:]

    label_start = start + len(body) + len(connector)
    label_end = label_start + len(chosen_clause)

    ex["id"] = f"{example['id']}_overgeneration"
    ex["original_output"] = original_output
    ex["output"] = new_output
    ex["hallucination_type"] = "overgeneration"
    ex["hallucination_labels"] = [
        make_label(
            start=label_start,
            end=label_end,
            text=chosen_clause,
            label_type="Unsupported Addition",
        )
    ]
    ex["hallucination_labels_processed"] = {
        "evident_conflict": 0,
        "baseless_info": 1,
    }
    ex["overgeneration_clause"] = chosen_clause
    ex["overgeneration_domain"] = detect_overgeneration_domain(example)
    ex["overgeneration_clause_source"] = clause_source

    validate_spans(ex)
    return ex


def inject_missing_tool(example: Dict, sentence: Optional[str] = None) -> Dict:
    sentence = sentence or choose_missing_tool_sentence(example)
    return append_hallucinated_sentence(
        example=example,
        sentence=sentence,
        label_type="Missing Tool",
        hallucination_type="missing_tool",
    )


def make_clean(example: Dict) -> Dict:
    ex = copy.deepcopy(example)
    ex["id"] = f"{example['id']}_clean"
    ex["hallucination_type"] = "clean"
    ex["hallucination_labels"] = []
    ex["hallucination_labels_processed"] = {
        "evident_conflict": 0,
        "baseless_info": 0,
    }
    validate_spans(ex)
    return ex


def load_overgeneration_cache(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    cache = {}
    for row in read_jsonl(path):
        cache[row["base_id"]] = row.get("clause") or row.get("sentence", "")
    return cache


def save_overgeneration_cache(path: Path, cache: Dict[str, str]) -> None:
    rows = [
        {"base_id": base_id, "clause": clause}
        for base_id, clause in sorted(cache.items())
    ]
    write_jsonl(path, rows)


def build_overgeneration_prompt(example: Dict) -> str:
    return (
        "Generate ONE unsupported clause for hallucination evaluation.\n"
        "Overgeneration = same topic as the query, but NOT stated in the tool context.\n\n"
        "GOOD:\n"
        "  the weather has been fairly stable over the past few months\n"
        "  demand for this route has remained strong throughout the season\n\n"
        "BAD (do NOT output these):\n"
        "  good clause: the weather is nice\n"
        "  would you like me to book a hotel\n"
        "  based on the tool output, the price is $50\n"
        "  can you also provide more details?\n"
        "  Stranger Things (ID: 80100172), The Witcher (ID: 80189685)\n\n"
        "Rules:\n"
        "- 6 to 16 words only\n"
        "- lowercase start, no trailing punctuation\n"
        "- no labels, no lists, no IDs, no quotes, no questions\n"
        "- no tool/API mentions, no action offers\n"
        "- return ONLY the clause text\n\n"
        f"Query:\n{example['query'][:600]}\n\n"
        f"Tool context:\n{example['context'][:900]}\n\n"
        f"Assistant response:\n{example['output'][:900]}\n"
    )


def normalize_overgeneration_sentence(text: str) -> str:
    return normalize_overgeneration_clause(text)


def generate_overgeneration_sentence_llm(example: Dict, client) -> str:
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_OVERGEN_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": "Return one clause only."},
            {"role": "user", "content": build_overgeneration_prompt(example)},
        ],
        temperature=0.9,
        max_tokens=80,
    )
    return normalize_overgeneration_clause(response.choices[0].message.content)


def build_overgeneration_sentences(
    examples: List[Dict],
    cache_path: Path,
    use_llm: bool = False,
) -> Dict[str, str]:
    cache = load_overgeneration_cache(cache_path)
    if not use_llm:
        return cache

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set; using template overgeneration sentences.")
        return cache

    try:
        from openai import OpenAI
    except ImportError:
        print("openai package not installed; using template overgeneration sentences.")
        return cache

    client = OpenAI(api_key=api_key)

    for example in examples:
        base_id = example["id"]
        if base_id in cache:
            continue
        try:
            cache[base_id] = generate_overgeneration_sentence_llm(example, client)
        except Exception as exc:
            print(f"LLM overgeneration failed for {base_id}: {exc}")
            cache[base_id] = random.choice(OVERGENERATION_CLAUSES_BY_DOMAIN["default"])
        save_overgeneration_cache(cache_path, cache)

    return cache
