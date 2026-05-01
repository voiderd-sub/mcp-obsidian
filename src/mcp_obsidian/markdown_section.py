"""Markdown section parsing for surgical heading-intro edits.

Defines `intro_region(text, heading_path)`: returns the line range
(start_line, end_line) of the **intro** of the targeted heading —
the content between the heading line and the first child heading
of strictly lower level (= deeper indent).

ATX headings only. Fenced code blocks are skipped (lines inside ``` blocks
are not parsed as headings, even if they start with `#`). Block-quoted
headings (`> ## foo`) are treated as content, not structural headings.
Setext headings (`====` underlines) are not yet supported (treated as
content).

heading_path uses `::` as delimiter (matches existing mcp-obsidian
conventions): e.g. `"H1 title::H2 title"` for nested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_ATX_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


@dataclass
class _Heading:
    line_idx: int
    level: int
    title: str


def _scan_headings(lines: list[str]) -> list[_Heading]:
    """Find all ATX headings, skipping lines inside fenced code blocks."""
    headings: list[_Heading] = []
    in_fence = False
    fence_marker = ""
    for i, line in enumerate(lines):
        m_fence = _FENCE_RE.match(line)
        if m_fence:
            marker = m_fence.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif fence_marker == marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        if line.lstrip().startswith(">"):
            continue
        m = _ATX_RE.match(line)
        if m:
            headings.append(_Heading(line_idx=i, level=len(m.group(1)), title=m.group(2).strip()))
    return headings


def _resolve_heading_path(headings: list[_Heading], heading_path: str) -> _Heading:
    """Resolve a `::`-delimited path to a single heading.

    Walks the heading list keeping track of nesting:
      - The next path segment must appear at a strictly deeper level than
        the prior matched heading, with no intervening heading at the same
        or shallower level (which would close the prior segment's section).

    Returns the matched leaf heading. Raises if 0 or >1 matches.
    """
    parts = [p.strip() for p in heading_path.split("::") if p.strip()]
    if not parts:
        raise ValueError("heading_path is empty")

    candidates: list[_Heading] = []
    n = len(headings)
    i = 0
    while i < n:
        h = headings[i]
        if h.title != parts[0]:
            i += 1
            continue
        # Try to walk the rest of the path under this h.
        if len(parts) == 1:
            candidates.append(h)
            i += 1
            continue
        cur_match = h
        cur_level = h.level
        depth = 1
        j = i + 1
        while j < n and depth < len(parts):
            hj = headings[j]
            if hj.level <= cur_level:
                break
            if hj.title == parts[depth] and hj.level == cur_level + 1:
                cur_match = hj
                cur_level = hj.level
                depth += 1
            j += 1
        if depth == len(parts):
            candidates.append(cur_match)
        i += 1

    if not candidates:
        raise ValueError(f"heading path {heading_path!r} not found")
    if len(candidates) > 1:
        locs = ", ".join(str(c.line_idx + 1) for c in candidates)
        raise ValueError(
            f"heading path {heading_path!r} matched {len(candidates)} times "
            f"(line numbers: {locs}); refine the path to be unique"
        )
    return candidates[0]


def intro_region(text: str, heading_path: str) -> tuple[int, int, list[str]]:
    """Return (start_idx, end_idx, lines) for the intro of the target heading.

    `start_idx` is the index of the first line **after** the heading line.
    `end_idx` is the index of the first child heading line (or len(lines)
    if the heading has no children and runs to EOF or to a sibling).

    The intro region is `lines[start_idx:end_idx]`. Slicing with these
    indices and substituting yields the new file content.
    """
    lines = text.splitlines(keepends=True)
    headings = _scan_headings(lines)
    target = _resolve_heading_path(headings, heading_path)

    start_idx = target.line_idx + 1
    end_idx = len(lines)
    for h in headings:
        if h.line_idx <= target.line_idx:
            continue
        if h.level <= target.level:
            # Sibling or shallower: end of the target's section entirely.
            end_idx = h.line_idx
            break
        if h.level == target.level + 1:
            # First direct child heading: end of intro.
            end_idx = h.line_idx
            break
        # Deeper child without an intervening direct child means there is
        # no direct child between target and this deeper heading; treat as
        # end of intro too (rare, malformed-ish, but be defensive).
        end_idx = h.line_idx
        break

    return start_idx, end_idx, lines


def apply_intro_op(text: str, heading_path: str, operation: str, content: str) -> str:
    """Apply append/prepend/replace to the intro region of the target heading.

    Returns the new full file text.
    """
    if operation not in {"append", "prepend", "replace"}:
        raise ValueError(f"unknown operation: {operation!r}")
    start_idx, end_idx, lines = intro_region(text, heading_path)
    if not content.endswith("\n"):
        content = content + "\n"

    if operation == "replace":
        new_intro_lines = [content]
    elif operation == "append":
        new_intro_lines = lines[start_idx:end_idx] + [content]
    else:  # prepend
        new_intro_lines = [content] + lines[start_idx:end_idx]

    return "".join(lines[:start_idx] + new_intro_lines + lines[end_idx:])


# ----------------------------------------------------------- harness helpers


_LEADING_HASH_RE = re.compile(r"^\s*#+\s*")


def normalize_heading_path(raw: str) -> str:
    """Strip leading `#+\\s*`, trailing `#*\\s*`, and surrounding whitespace.

    Operates on a single `::` segment. Idempotent. Used by patch_content /
    section_intro_patch leniency: `'## Architecture'` -> `'Architecture'`,
    `'  Sub  '` -> `'Sub'`, `'Foo ##'` -> `'Foo'`.
    """
    s = _LEADING_HASH_RE.sub("", raw)
    s = re.sub(r"\s*#*\s*$", "", s)
    return s.strip()


def heading_tree_lines(text: str, max_count: int = 50) -> list[str]:
    """Return indented heading-tree representation as text lines.

    Each line: `('  ' * (level - 1)) + '- ' + title`. If headings exceed
    `max_count`, the last entry is `'... (N more)'`. If the text has no
    headings, returns `['(no headings)']`.

    Used in healing messages to let agents self-correct heading paths.
    """
    headings = _scan_headings(text.splitlines(keepends=True))
    if not headings:
        return ["(no headings)"]

    out: list[str] = []
    for h in headings[:max_count]:
        indent = "  " * (h.level - 1)
        out.append(f"{indent}- {h.title}")
    if len(headings) > max_count:
        out.append(f"... ({len(headings) - max_count} more)")
    return out


def section_region(text: str, heading_path: str) -> tuple[int, int, list[str]]:
    """Return (start_idx, end_idx, lines) for the entire section.

    Unlike `intro_region`, the range covers the heading line itself plus
    the intro plus all descendant subsections. `end_idx` is the line index
    of the first sibling or shallower heading after the target, or
    `len(lines)` if none.

    Used by `get_section_content` and by the (heading, replace)
    confirm_wipe gate to know what would be wiped.
    """
    lines = text.splitlines(keepends=True)
    headings = _scan_headings(lines)
    target = _resolve_heading_path(headings, heading_path)

    start_idx = target.line_idx
    end_idx = len(lines)
    for h in headings:
        if h.line_idx <= target.line_idx:
            continue
        if h.level <= target.level:
            end_idx = h.line_idx
            break

    return start_idx, end_idx, lines


def heading_has_children(text: str, heading_path: str) -> bool:
    """True if the resolved heading has at least one descendant heading
    before the next sibling/shallower heading.

    Used by patch_content (heading, replace) to decide whether to demand
    `confirm_wipe=true`. Raises ValueError (via _resolve_heading_path) if
    the path is missing or ambiguous — caller should translate to healing.
    """
    lines = text.splitlines(keepends=True)
    headings = _scan_headings(lines)
    target = _resolve_heading_path(headings, heading_path)

    for h in headings:
        if h.line_idx <= target.line_idx:
            continue
        if h.level <= target.level:
            return False
        # h.level > target.level → at least one descendant exists
        return True
    return False


def resolve_to_full_path(text: str, heading_path: str) -> str:
    """Resolve a (possibly partial) heading_path to its full '::'-delimited
    path from the H1 root.

    Used by patch_content (heading) to convert agent-provided paths
    (e.g. 'Section B' or '## Section B') into the full path Obsidian REST
    requires (e.g. 'Test Root::Section B').

    - Single-segment input (e.g. 'Section B') → matched if unique anywhere
      in the file; returns the full ancestor chain.
    - Multi-segment input (e.g. 'Top::Sub') → resolved as before; returns
      the full chain ending at the resolved leaf (so a partial path like
      'Sub::Leaf' that omits the H1 ancestor is auto-completed).
    - If already a full root-anchored path, returns it unchanged.

    Raises ValueError on missing or ambiguous paths (matches existing
    _resolve_heading_path semantics).
    """
    lines = text.splitlines(keepends=True)
    headings = _scan_headings(lines)
    target = _resolve_heading_path(headings, heading_path)

    # Walk back through `headings` to build the ancestor chain ending at target.
    chain: list[str] = [target.title]
    current_level = target.level
    for h in reversed(headings):
        if h.line_idx >= target.line_idx:
            continue
        if h.level < current_level:
            chain.append(h.title)
            current_level = h.level
            if current_level == 1:
                break

    chain.reverse()
    return "::".join(chain)


def count_descendant_headings(text: str, heading_path: str) -> int:
    """Count descendant headings under the target heading (any depth)
    before the next sibling/shallower heading. Used in confirm_wipe
    error messages to tell the agent how many would be lost.
    """
    lines = text.splitlines(keepends=True)
    headings = _scan_headings(lines)
    target = _resolve_heading_path(headings, heading_path)

    n = 0
    for h in headings:
        if h.line_idx <= target.line_idx:
            continue
        if h.level <= target.level:
            break
        n += 1
    return n
