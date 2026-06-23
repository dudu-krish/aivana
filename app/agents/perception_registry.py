"""Registry of Perception (input) micro-agents."""

from __future__ import annotations

from typing import Any

PERCEPTION_AGENTS: dict[str, dict[str, Any]] = {
    "read-text": {
        "name": "Read Text",
        "task": "Read and normalize plain text input.",
        "keywords": ["read text", "plain text", "text file", "text input"],
        "input_hint": "Paste or type text to read.",
    },
    "read-pdf": {
        "name": "Read PDF",
        "task": "Read every PDF in a folder and extract text from each document.",
        "keywords": ["pdf", "read pdf", "pdf folder", "pdf documents", "batch pdf"],
        "input_hint": "Folder path (e.g. gmail_attachments, downloads, invoices).",
        "uses_folder": True,
    },
    "read-word": {
        "name": "Read Word Document",
        "task": "Extract text from a Word (.docx) document.",
        "keywords": ["word", "docx", "document", "microsoft word"],
        "input_hint": "Path to a .docx file in downloads/invoices, or pasted content.",
    },
    "read-excel": {
        "name": "Read Excel",
        "task": "Read spreadsheet data from Excel files.",
        "keywords": ["excel", "xlsx", "spreadsheet", "workbook"],
        "input_hint": "Path to .xlsx/.xls under your workspace.",
    },
    "read-csv": {
        "name": "Read CSV",
        "task": "Parse CSV content into rows and columns.",
        "keywords": ["csv", "comma separated", "spreadsheet csv"],
        "input_hint": "CSV file path or paste CSV content.",
    },
    "read-image": {
        "name": "Read Image",
        "task": "Inspect image files and extract basic metadata.",
        "keywords": ["image", "photo", "png", "jpg", "jpeg"],
        "input_hint": "Image file path or URL.",
    },
    "ocr": {
        "name": "OCR",
        "task": "Optical character recognition on images or scanned text.",
        "keywords": ["ocr", "scan", "optical character", "scanned document"],
        "input_hint": "Image path or pasted text from a scan.",
    },
    "read-barcode": {
        "name": "Read Barcode",
        "task": "Detect and decode barcode values from input.",
        "keywords": ["barcode", "upc", "ean", "scan barcode"],
        "input_hint": "Barcode number or image path.",
    },
    "read-qr-code": {
        "name": "Read QR Code",
        "task": "Decode QR code payloads from text or URLs.",
        "keywords": ["qr", "qr code", "qrcode"],
        "input_hint": "QR payload text, URL, or image path.",
    },
    "read-audio": {
        "name": "Read Audio",
        "task": "Inspect audio files and extract metadata.",
        "keywords": ["audio", "mp3", "wav", "sound file"],
        "input_hint": "Audio file path under your workspace.",
    },
    "speech-to-text": {
        "name": "Speech-to-Text",
        "task": "Transcribe spoken audio into text.",
        "keywords": ["speech to text", "transcribe", "transcription", "stt"],
        "input_hint": "Audio file path or pasted transcript draft.",
    },
    "video-frame-extractor": {
        "name": "Video Frame Extractor",
        "task": "Extract representative frames or timestamps from video.",
        "keywords": ["video frame", "extract frame", "video snapshot"],
        "input_hint": "Video file path or description.",
    },
    "face-detector": {
        "name": "Face Detector",
        "task": "Detect faces mentioned or described in visual input.",
        "keywords": ["face", "face detection", "faces in image"],
        "input_hint": "Image path or description of faces to detect.",
    },
    "object-detector": {
        "name": "Object Detector",
        "task": "Detect objects described in visual or text input.",
        "keywords": ["object detection", "detect objects", "vision"],
        "input_hint": "Image path or object description.",
    },
    "handwriting-reader": {
        "name": "Handwriting Reader",
        "task": "Interpret handwritten text from scans or descriptions.",
        "keywords": ["handwriting", "handwritten", "cursive"],
        "input_hint": "Scanned text or image path.",
    },
    "table-detector": {
        "name": "Table Detector",
        "task": "Detect and structure tabular data in input.",
        "keywords": ["table", "tabular", "grid data", "rows columns"],
        "input_hint": "HTML, CSV, or text containing a table.",
    },
    "form-reader": {
        "name": "Form Reader",
        "task": "Extract labeled fields from forms.",
        "keywords": ["form", "fields", "application form", "questionnaire"],
        "input_hint": "Form text with field labels and values.",
    },
    "screenshot-reader": {
        "name": "Screenshot Reader",
        "task": "Read text and UI elements from screenshots.",
        "keywords": ["screenshot", "screen capture", "screen grab"],
        "input_hint": "Screenshot file path or pasted OCR text.",
    },
    "html-reader": {
        "name": "HTML Reader",
        "task": "Parse HTML and extract visible text and links.",
        "keywords": ["html", "web page", "markup", "parse html"],
        "input_hint": "HTML snippet, URL, or file path.",
    },
    "email-reader": {
        "name": "Email Reader",
        "task": "Parse email headers, body, and attachments metadata.",
        "keywords": ["read email", "email body", "email headers", "mime"],
        "input_hint": "Raw email text or .eml content.",
    },
    "calendar-reader": {
        "name": "Calendar Reader",
        "task": "Parse calendar events from ICS or event text.",
        "keywords": ["calendar", "ics", "events", "schedule file"],
        "input_hint": "ICS content, event list, or calendar export.",
    },
    "database-reader": {
        "name": "Database Reader",
        "task": "Parse structured database rows from JSON or SQL output.",
        "keywords": ["database", "sql result", "db rows", "query output"],
        "input_hint": "JSON rows or SQL result text.",
    },
    "api-reader": {
        "name": "API Reader",
        "task": "Fetch and parse JSON from an HTTP API endpoint.",
        "keywords": ["api", "rest", "endpoint", "fetch json", "http get"],
        "input_hint": "API URL (https://...).",
    },
    "log-reader": {
        "name": "Log Reader",
        "task": "Parse log lines into structured entries.",
        "keywords": ["log", "logs", "log file", "server log"],
        "input_hint": "Log file path or pasted log lines.",
    },
    "clipboard-reader": {
        "name": "Clipboard Reader",
        "task": "Normalize clipboard-style pasted content.",
        "keywords": ["clipboard", "paste", "copied text"],
        "input_hint": "Paste clipboard content here.",
    },
}


def is_perception_agent(agent_id: str) -> bool:
    return agent_id in PERCEPTION_AGENTS


def agent_name(agent_id: str) -> str:
    meta = PERCEPTION_AGENTS.get(agent_id)
    return meta["name"] if meta else agent_id
