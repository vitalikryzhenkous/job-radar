"""raw/*.txt -> jd.md: убрать шум, разложить по секциям, отметить обрезку."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DICTS = Path(__file__).parent / "dicts"
SECTIONS = ("about", "responsibilities", "requirements", "nice", "offer")
TITLES = {"about": "About", "responsibilities": "Responsibilities", "requirements": "Requirements",
          "nice": "Nice to have", "offer": "Offer"}
BULLET = re.compile(r"^\s*[*•\-–]\s*")
GREETING = re.compile(r"^(hi|hello|dear|hey|good (morning|afternoon))\b[\s,]*([A-ZА-ЯЁ][\w-]+)?", re.I)
SIGNOFF = re.compile(r"^(thanks|thank you|regards|best( regards)?|cheers|kind regards)\b", re.I)
TERMINAL = tuple(".!?)]»\"'”:;")


def _load(name: str) -> dict:
    return yaml.safe_load((DICTS / name).read_text(encoding="utf-8"))


_NOISE = _load("noise.yaml")
NOISE_LINES = [re.compile(rf"^(?:{p})$", re.I) for p in _NOISE["lines"]]
NOISE_TAILS = [re.compile(p, re.I) for p in _NOISE["tails"]]
HEADINGS = [(sec, re.compile(rf"^(?:{p})\s*:?\s*", re.I))
            for sec, pats in _load("sections.yaml").items() for p in pats]


@dataclass
class Message:
    name: str
    source: str
    lines: list[str]
    greeting_name: str | None = None
    truncated: bool = False


@dataclass
class Normalized:
    messages: list[Message]
    header: list[str] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)

    @property
    def outreach(self) -> bool:
        return any(m.greeting_name or GREETING.match(m.lines[0] if m.lines else "") for m in self.messages)

    @property
    def truncated(self) -> bool:
        return any(m.truncated for m in self.messages)

    def text(self) -> str:
        return "\n".join(line for m in self.messages for line in m.lines)


def clean_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        for tail in NOISE_TAILS:
            line = tail.sub("", line).strip()
        if line and not any(p.match(line) for p in NOISE_LINES):
            out.append(line)
    return out


def is_truncated(lines: list[str]) -> bool:
    """Обрезка: анонсированный список без содержимого или оборванная длинная последняя строка."""
    for i, line in enumerate(lines):
        if line.endswith(":") and len(line) > 30:
            nxt = next((n for n in lines[i + 1:] if n), None)
            if nxt is None or SIGNOFF.match(nxt):
                return True
    last = lines[-1] if lines else ""
    return len(lines) > 3 and len(last) > 40 and not last.endswith(TERMINAL)


def _heading(line: str) -> tuple[str, str] | None:
    body = BULLET.sub("", line)
    for sec, pat in HEADINGS:
        m = pat.match(body)
        if m and (len(body) - m.end() == 0 or line.rstrip().endswith(":") or len(body) > 60
                  or body[:m.end()].rstrip().endswith(":")):
            return sec, body[m.end():].strip()
    return None


def split_sections(lines: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    header, sections, cur = [], {}, None
    for line in lines:
        h = _heading(line)
        if h:
            cur, rest = h
            sections.setdefault(cur, [])
            if rest:
                sections[cur].append(rest)
            continue
        if SIGNOFF.match(line):
            cur = None
            continue
        (sections.setdefault(cur, []) if cur else header).append(BULLET.sub("", line))
    return header, sections


def normalize(raw_files: list[Path]) -> Normalized:
    messages = []
    for p in sorted(raw_files):
        lines = clean_lines(p.read_text(encoding="utf-8"))
        g = next((GREETING.match(x) for x in lines[:2] if GREETING.match(x)), None)
        source = p.stem.split("-", 1)[1] if "-" in p.stem else "text"
        messages.append(Message(p.name, source, lines, g.group(3) if g else None, is_truncated(lines)))
    header, sections = [], {}
    for m in messages:
        h, s = split_sections(m.lines)
        header += h
        for k, v in s.items():
            sections.setdefault(k, []).extend(v)
    return Normalized(messages, header, sections)


def to_markdown(n: Normalized) -> str:
    out = [f"<!-- sources: {', '.join(m.name for m in n.messages)}; truncated: {n.truncated} -->"]
    if n.header:
        out += ["## Header", *n.header, ""]
    for sec in SECTIONS:
        if n.sections.get(sec):
            out += [f"## {TITLES[sec]}", *(f"- {x}" for x in n.sections[sec]), ""]
    return "\n".join(out).rstrip() + "\n"
