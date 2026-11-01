"""Words that label a numbered thing ("Phase 2", "Exhibit 2.1", "page 7").

A digit right after one of these words is a label, not a quantity, so the
number reader does not count it. The list is closed and holds only the words
our own renderers number. A word is added here only together with a renderer
that numbers it, because every word on the list is a place for a stray digit
to hide: "Option 3" passes the law only because we draw "Option 3" ourselves.
"""
from __future__ import annotations

LABEL_WORDS: tuple[str, ...] = (
    "phase", "step", "section", "exhibit", "volume", "page", "module", "screen",
    "part", "appendix", "table", "slide", "footnote", "option",
    # the structure words the roadmap prompts name (Task 9 names them in the prompts)
    "tier", "stage", "level", "gate", "wave", "sprint", "round", "milestone",
)

# Names in the technical register whose number is part of the name, not a
# quantity: "ISO 27001", "SOC 2", "TLS 1.3", "Python 3.12", "HTTP 429", "Port
# 5432". The number (or dotted version) right after one of these is an
# identifier; a quantity after it is still read ("ISO 27001 costs $5,000"). The
# list is closed like LABEL_WORDS: every name on it is a place a stray digit can
# hide, so add one only for the technical volume's own vocabulary. Matched case
# insensitively.
TECH_NAMES: tuple[str, ...] = (
    "iso", "iec", "soc", "gdpr", "article", "annex", "hipaa", "pci", "dss", "nist", "rfc", "tls", "ssl",
    "oauth", "oidc", "saml", "wcag", "http", "https", "port", "ipv", "python", "postgresql", "mysql",
    "sqlite", "react", "node", "java", "django", "rails", "linux", "ubuntu", "debian", "ios", "android",
    "windows", "macos", "php", "excel", "office", "ecmascript", "html", "css", "wi-fi", "bluetooth", "usb",
    "docker", "kubernetes", "postgres", "redis", "vue", "angular", "next.js", "tailwind",
)
