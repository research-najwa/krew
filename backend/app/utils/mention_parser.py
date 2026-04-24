"""@mention parser -- extracts agent mentions from chat messages."""
import re
from typing import Optional

# Canonical agent name -> all recognized mention strings
# Keys must match orchestrator.AGENTS keys exactly.
# Arabic names must match BaseAgent.name_ar for each agent.
AGENT_ALIASES: dict[str, list[str]] = {
    "deema":    ["deema", "ديمة", "dima", "ديما"],
    "waleed":   ["waleed", "وليد", "walid"],
    "mohammad": ["mohammad", "محمد", "mohammed", "mohamad"],
    "yara":     ["yara", "يارا"],
    "ahmad":    ["ahmad", "أحمد", "ahmed"],
}

# Inverted lookup: mention_string -> canonical_name (built once at import time)
MENTION_TO_AGENT: dict[str, str] = {}
for _canonical, _aliases in AGENT_ALIASES.items():
    for _alias in _aliases:
        MENTION_TO_AGENT[_alias.lower()] = _canonical

# For dynamic/deployed agents, the format is @dept:{uuid} which is handled separately.

# Unicode property ranges:
#   \w          -- ASCII word chars (a-z, A-Z, 0-9, _)
#   \u0600-\u06FF -- Arabic block (covers all Arabic letters + common diacritics)
#   \u0750-\u077F -- Arabic Supplement
#   \u08A0-\u08FF -- Arabic Extended-A
#   \uFE70-\uFEFF -- Arabic Presentation Forms-B
#
# The colon and hyphen after @ allow matching dept:{uuid} format.
# The pattern requires @ preceded by start-of-string or whitespace to avoid matching
# email addresses (e.g., user@deema.com).

_MENTION_RE = re.compile(
    r'(?:^|(?<=\s))'           # Must be at start or after whitespace
    r'@'                        # The @ trigger
    r'('                        # Begin capture group
    r'[\w\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFE70-\uFEFF]+'  # Agent name
    r'(?::[\w-]+)?'             # Optional :suffix for dept:{uuid}
    r')',                        # End capture group
    re.UNICODE | re.IGNORECASE
)

# Arabic diacritics (tashkeel) to strip before lookup
_DIACRITICS_RE = re.compile(r'[\u064B-\u065F\u0670]')


def _normalize_alef(text: str) -> str:
    """Replace all alef variants (إ أ آ ٱ) with bare alef (ا) for fuzzy Arabic matching."""
    return text.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا").replace("ٱ", "ا")


def parse_mention(message: str) -> tuple[str | None, str]:
    """
    Extract the first @agent mention from a chat message.

    Returns:
        (canonical_agent_name, cleaned_message) if a valid @mention is found.
        (None, original_message) if no @mention or unrecognized agent.

    The cleaned_message has the @mention stripped and whitespace normalized.
    For unrecognized @mentions, returns (None, original_message) -- the caller
    (orchestrator) is responsible for producing the error message, since it
    has access to the employee's available agents list.

    Examples:
        >>> parse_mention("@deema check my leave")
        ("deema", "check my leave")
        >>> parse_mention("@ديمة كم رصيد إجازاتي؟")
        ("deema", "كم رصيد إجازاتي؟")
        >>> parse_mention("hey @mohammad schedule interview")
        ("mohammad", "hey schedule interview")
        >>> parse_mention("@AHMAD show analytics")
        ("ahmad", "show analytics")
        >>> parse_mention("no mention here")
        (None, "no mention here")
        >>> parse_mention("@unknown do something")
        (None, "@unknown do something")
        >>> parse_mention("@dept:550e8400-e29b-41d4-a716-446655440000 help")
        ("dept:550e8400-e29b-41d4-a716-446655440000", "help")
    """
    match = _MENTION_RE.search(message)
    if not match:
        return None, message

    raw_name = match.group(1)

    # Handle dept:{uuid} format -- pass through as-is (validated by orchestrator)
    if raw_name.lower().startswith("dept:"):
        cleaned = (message[:match.start()] + message[match.end():]).strip()
        cleaned = re.sub(r'\s{2,}', ' ', cleaned)
        return raw_name.lower(), cleaned

    # Strip Arabic diacritics, normalize alef variants, and lowercase for lookup
    normalized = _DIACRITICS_RE.sub('', raw_name).lower()
    normalized = _normalize_alef(normalized)

    agent_name = MENTION_TO_AGENT.get(normalized)
    if not agent_name:
        # Retry with alef-normalized keys (handles أحمد vs احمد etc.)
        for alias, canonical in MENTION_TO_AGENT.items():
            if _normalize_alef(alias) == normalized:
                agent_name = canonical
                break
    if not agent_name:
        # Unrecognized mention -- return None so orchestrator can produce error
        return None, message

    # Strip the @mention from the message
    cleaned = (message[:match.start()] + message[match.end():]).strip()
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)  # Collapse double spaces

    return agent_name, cleaned


def get_mentioned_raw(message: str) -> str | None:
    """Return the raw @mention string (e.g., '@deema', '@أحمد') for error messages.

    Returns None if no @mention found.
    """
    match = _MENTION_RE.search(message)
    return f"@{match.group(1)}" if match else None
