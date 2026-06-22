"""Registry of Understanding micro-agents."""

from __future__ import annotations

from typing import Any

UNDERSTANDING_AGENTS: dict[str, dict[str, Any]] = {
    "intent-detection": {
        "name": "Intent Detection",
        "task": "Detect the primary user intent(s) in the text.",
        "keywords": ["intent", "intention", "what does the user want"],
    },
    "topic-detection": {
        "name": "Topic Detection",
        "task": "Identify the main topic(s) discussed in the text.",
        "keywords": ["topic", "subject", "theme", "about what"],
    },
    "language-detection": {
        "name": "Language Detection",
        "task": "Detect the language of the text.",
        "keywords": ["language", "locale", "what language"],
    },
    "entity-extraction": {
        "name": "Entity Extraction",
        "task": "Extract named entities (people, places, organizations, etc.).",
        "keywords": ["entity", "entities", "named entity", "ner"],
    },
    "keyword-extraction": {
        "name": "Keyword Extraction",
        "task": "Extract the most important keywords and phrases.",
        "keywords": ["keyword", "keywords", "key phrases", "terms"],
    },
    "relationship-extraction": {
        "name": "Relationship Extraction",
        "task": "Extract relationships between entities in the text.",
        "keywords": ["relationship", "relation", "connected to", "link between"],
    },
    "event-detection": {
        "name": "Event Detection",
        "task": "Detect events mentioned in the text.",
        "keywords": ["event", "happened", "occurrence", "incident"],
    },
    "date-extraction": {
        "name": "Date Extraction",
        "task": "Extract dates and time expressions from the text.",
        "keywords": ["date", "when", "deadline", "schedule"],
    },
    "location-extraction": {
        "name": "Location Extraction",
        "task": "Extract locations, addresses, and geographic references.",
        "keywords": ["location", "where", "address", "place", "city"],
    },
    "person-extraction": {
        "name": "Person Extraction",
        "task": "Extract person names and roles mentioned in the text.",
        "keywords": ["person", "people", "who", "contact name"],
    },
    "organization-extraction": {
        "name": "Organization Extraction",
        "task": "Extract organizations, companies, and institutions.",
        "keywords": ["organization", "company", "vendor", "firm", "business"],
    },
    "product-extraction": {
        "name": "Product Extraction",
        "task": "Extract products, SKUs, and service names.",
        "keywords": ["product", "sku", "item", "service name"],
    },
    "emotion-detection": {
        "name": "Emotion Detection",
        "task": "Detect emotions expressed in the text.",
        "keywords": ["emotion", "feeling", "angry", "happy", "frustrated"],
    },
    "sentiment-detection": {
        "name": "Sentiment Detection",
        "task": "Classify overall sentiment (positive, negative, neutral).",
        "keywords": ["sentiment", "positive", "negative", "tone"],
    },
    "urgency-detection": {
        "name": "Urgency Detection",
        "task": "Assess how urgent the message or request is.",
        "keywords": ["urgent", "urgency", "asap", "priority", "immediate"],
    },
    "risk-detection": {
        "name": "Risk Detection",
        "task": "Identify potential risks, compliance issues, or red flags.",
        "keywords": ["risk", "compliance", "fraud", "security", "red flag"],
    },
    "spam-detection": {
        "name": "Spam Detection",
        "task": "Determine whether the text looks like spam or unwanted mail.",
        "keywords": ["spam", "junk", "phishing", "unsolicited"],
    },
    "duplicate-detection": {
        "name": "Duplicate Detection",
        "task": "Compare input text to reference text and detect duplication.",
        "keywords": ["duplicate", "dupe", "same as", "copy of"],
        "needs_reference": True,
    },
    "similarity-detection": {
        "name": "Similarity Detection",
        "task": "Score semantic/textual similarity between two texts.",
        "keywords": ["similar", "similarity", "match score", "alike"],
        "needs_reference": True,
    },
    "root-cause-finder": {
        "name": "Root Cause Finder",
        "task": "Infer likely root causes from problem descriptions.",
        "keywords": ["root cause", "why", "reason", "underlying issue"],
    },
}


def is_understanding_agent(agent_id: str) -> bool:
    return agent_id in UNDERSTANDING_AGENTS


def agent_name(agent_id: str) -> str:
    meta = UNDERSTANDING_AGENTS.get(agent_id)
    return meta["name"] if meta else agent_id
