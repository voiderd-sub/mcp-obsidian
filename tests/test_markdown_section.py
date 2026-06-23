"""Unit tests for markdown_section.intro_region / apply_intro_op."""

from __future__ import annotations

import sys
import pathlib
import importlib.util

# Import markdown_section directly without triggering the package __init__
# (which would require OBSIDIAN_API_KEY).
_PKG = pathlib.Path(__file__).resolve().parent.parent / "src" / "mcp_obsidian"
_spec = importlib.util.spec_from_file_location(
    "markdown_section", str(_PKG / "markdown_section.py")
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["markdown_section"] = _mod
_spec.loader.exec_module(_mod)
apply_intro_op = _mod.apply_intro_op
intro_region = _mod.intro_region
normalize_heading_path = _mod.normalize_heading_path
heading_tree_lines = _mod.heading_tree_lines
section_region = _mod.section_region
heading_has_children = _mod.heading_has_children
count_descendant_headings = _mod.count_descendant_headings
resolve_to_full_path = _mod.resolve_to_full_path
apply_section_op = _mod.apply_section_op
rename_heading = _mod.rename_heading
delete_section = _mod.delete_section
heading_level = _mod.heading_level
leading_heading_level = _mod.leading_heading_level


# ----------------------------------------------------------------- intro_region


def test_intro_region_h1_with_h2_children():
    text = (
        "# Dashboard\n"
        "\n"
        "> 최종 업데이트: old\n"
        "\n"
        "## 진행 중\n"
        "child content\n"
    )
    s, e, lines = intro_region(text, "Dashboard")
    assert "".join(lines[s:e]) == "\n> 최종 업데이트: old\n\n"


def test_intro_region_no_children_runs_to_eof():
    text = "# Only\n\nintro paragraph\n"
    s, e, lines = intro_region(text, "Only")
    assert "".join(lines[s:e]) == "\nintro paragraph\n"


def test_intro_region_nested_path():
    text = (
        "# A\n"
        "intro of A\n"
        "## B\n"
        "intro of B\n"
        "### C\n"
        "intro of C\n"
        "## D\n"
        "intro of D\n"
    )
    # Path A::B
    s, e, lines = intro_region(text, "A::B")
    assert "".join(lines[s:e]) == "intro of B\n"


def test_intro_region_skips_code_block_pseudo_heading():
    text = (
        "# Real\n"
        "before\n"
        "```\n"
        "## fake\n"
        "```\n"
        "after\n"
        "## ChildReal\n"
        "child body\n"
    )
    s, e, lines = intro_region(text, "Real")
    body = "".join(lines[s:e])
    assert "## fake" in body
    assert "## ChildReal" not in body
    assert body.endswith("after\n")


def test_intro_region_ignores_blockquote_heading():
    text = (
        "# H\n"
        "intro line\n"
        "> ## quoted not heading\n"
        "more intro\n"
        "## RealChild\n"
        "child\n"
    )
    s, e, lines = intro_region(text, "H")
    body = "".join(lines[s:e])
    assert "> ## quoted not heading" in body
    assert "more intro" in body
    assert "## RealChild" not in body


def test_intro_region_missing_path_raises():
    text = "# A\nbody\n"
    try:
        intro_region(text, "B")
    except ValueError as e:
        assert "not found" in str(e)
    else:
        assert False, "expected ValueError"


def test_intro_region_ambiguous_path_raises():
    text = "# A\nbody1\n# A\nbody2\n"
    try:
        intro_region(text, "A")
    except ValueError as e:
        assert "matched 2 times" in str(e)
    else:
        assert False, "expected ValueError"


# --------------------------------------------------------------- apply_intro_op


def test_apply_intro_op_replace_preserves_children():
    text = (
        "# Dashboard\n"
        "\n"
        "> 최종 업데이트: 2026-04-21 19:30\n"
        "\n"
        "## 진행 중\n"
        "\n"
        "### Project A\n"
        "details\n"
    )
    out = apply_intro_op(
        text,
        heading_path="Dashboard",
        operation="replace",
        content="> 최종 업데이트: 2026-04-22 10:00",
    )
    assert "## 진행 중" in out
    assert "### Project A" in out
    assert "details" in out
    assert "> 최종 업데이트: 2026-04-22 10:00" in out
    assert "2026-04-21 19:30" not in out


def test_apply_intro_op_append_inserts_before_first_child():
    text = (
        "# H\n"
        "first line\n"
        "## child\n"
        "child body\n"
    )
    out = apply_intro_op(text, "H", "append", "added at end of intro")
    expected = (
        "# H\n"
        "first line\n"
        "added at end of intro\n"
        "## child\n"
        "child body\n"
    )
    assert out == expected


def test_apply_intro_op_prepend_inserts_after_heading_line():
    text = (
        "# H\n"
        "first line\n"
        "## child\n"
        "child body\n"
    )
    out = apply_intro_op(text, "H", "prepend", "new top line")
    expected = (
        "# H\n"
        "new top line\n"
        "first line\n"
        "## child\n"
        "child body\n"
    )
    assert out == expected


def test_apply_intro_op_replace_with_no_children_replaces_to_eof():
    text = "# Only\nold body\n"
    out = apply_intro_op(text, "Only", "replace", "new body")
    assert out == "# Only\nnew body\n"


# --------------------------------------------------------- normalize_heading_path


def test_normalize_strips_leading_hashes():
    assert normalize_heading_path("## Architecture") == "Architecture"
    assert normalize_heading_path("### Sub Sub") == "Sub Sub"
    assert normalize_heading_path("# Top") == "Top"


def test_normalize_strips_whitespace():
    assert normalize_heading_path("  Architecture  ") == "Architecture"
    assert normalize_heading_path("\tSub\t") == "Sub"


def test_normalize_idempotent():
    s1 = normalize_heading_path("## Architecture  ")
    s2 = normalize_heading_path(s1)
    assert s1 == s2 == "Architecture"


def test_normalize_strips_trailing_hashes():
    # ATX heading optional closing `#`s — handle gracefully
    assert normalize_heading_path("## Heading ##") == "Heading"


def test_normalize_passthrough_when_clean():
    assert normalize_heading_path("Architecture") == "Architecture"
    assert normalize_heading_path("My H1") == "My H1"


# --------------------------------------------------------- heading_tree_lines


def test_heading_tree_basic_indent():
    text = (
        "# Top\n"
        "intro\n"
        "## Sub\n"
        "body\n"
        "### Leaf\n"
        "x\n"
        "# Another\n"
    )
    lines = heading_tree_lines(text)
    assert lines == [
        "- Top",
        "  - Sub",
        "    - Leaf",
        "- Another",
    ]


def test_heading_tree_empty():
    assert heading_tree_lines("no headings here\nat all\n") == ["(no headings)"]


def test_heading_tree_truncates():
    text = "".join(f"# H{i}\n" for i in range(60))
    lines = heading_tree_lines(text, max_count=50)
    assert len(lines) == 51
    assert lines[-1] == "... (10 more)"


# --------------------------------------------------------- section_region


def test_section_region_no_children():
    text = "# Top\nintro\n# Other\nx\n"
    s, e, lines = section_region(text, "Top")
    assert "".join(lines[s:e]) == "# Top\nintro\n"


def test_section_region_with_children_includes_them():
    text = (
        "# Top\n"
        "intro\n"
        "## Child A\n"
        "a body\n"
        "### Grand\n"
        "g body\n"
        "## Child B\n"
        "b body\n"
        "# Sibling\n"
        "s body\n"
    )
    s, e, lines = section_region(text, "Top")
    body = "".join(lines[s:e])
    assert "# Top\n" in body
    assert "## Child A" in body
    assert "### Grand" in body
    assert "## Child B" in body
    assert "# Sibling" not in body


def test_section_region_runs_to_eof_when_no_sibling():
    text = "# Top\nintro\n## Child\nx\n"
    s, e, lines = section_region(text, "Top")
    assert e == len(lines)


def test_section_region_nested_path():
    text = "# A\n## B\nb1\n### C\nc body\n## D\nd body\n"
    s, e, lines = section_region(text, "A::B")
    body = "".join(lines[s:e])
    assert "## B\n" in body
    assert "### C" in body
    assert "## D" not in body


# --------------------------------------------------------- heading_has_children


def test_heading_has_children_true():
    text = "# Top\nintro\n## Sub\nx\n"
    assert heading_has_children(text, "Top") is True


def test_heading_has_children_false_leaf():
    text = "# Top\nintro\n## Sub\nx\n"
    assert heading_has_children(text, "Top::Sub") is False


def test_heading_has_children_false_no_descendants():
    text = "# Only\nbody\n"
    assert heading_has_children(text, "Only") is False


def test_heading_has_children_stops_at_sibling():
    # A has body but no children, B follows as sibling
    text = "# A\nbody\n# B\n## B-sub\n"
    assert heading_has_children(text, "A") is False
    assert heading_has_children(text, "B") is True


# ------------------------------------------------------- count_descendant_headings


def test_count_descendants_zero():
    text = "# Top\nbody\n"
    assert count_descendant_headings(text, "Top") == 0


def test_count_descendants_multi_level():
    text = (
        "# Top\n"
        "## A\n"
        "### A1\n"
        "### A2\n"
        "## B\n"
        "# Sibling\n"
        "## not-counted\n"
    )
    # Top has descendants: A, A1, A2, B = 4 (Sibling and its child excluded)
    assert count_descendant_headings(text, "Top") == 4


# --------------------------------------------------------- resolve_to_full_path


def test_resolve_full_path_single_unique_name():
    text = "# Top\n## Section A\nx\n## Section B\ny\n"
    assert resolve_to_full_path(text, "Section B") == "Top::Section B"


def test_resolve_full_path_already_full():
    text = "# Top\n## Section A\nx\n## Section B\ny\n"
    assert resolve_to_full_path(text, "Top::Section B") == "Top::Section B"


def test_resolve_full_path_partial_chain_completed():
    text = "# Top\n## A\n### Leaf\nx\n## B\n"
    # 'A::Leaf' omits Top; should be completed
    assert resolve_to_full_path(text, "A::Leaf") == "Top::A::Leaf"


def test_resolve_full_path_h1_alone():
    text = "# Top\nintro\n## Sub\n"
    assert resolve_to_full_path(text, "Top") == "Top"


def test_resolve_full_path_ambiguous_raises():
    text = "# A\nx\n# B\n## Dup\ny\n# C\n## Dup\nz\n"
    try:
        resolve_to_full_path(text, "Dup")
    except ValueError as e:
        assert "matched 2 times" in str(e)
    else:
        assert False, "expected ValueError"


def test_resolve_full_path_missing_raises():
    text = "# Top\n## A\n"
    try:
        resolve_to_full_path(text, "Nonexistent")
    except ValueError as e:
        assert "not found" in str(e)
    else:
        assert False, "expected ValueError"


def test_resolve_full_path_deeply_nested_unique_leaf():
    text = "# A\n## B\n### C\n#### D\nx\n"
    assert resolve_to_full_path(text, "D") == "A::B::C::D"


# --------------------------------------------------------------- apply_section_op


def test_apply_section_op_replace_wipes_children():
    text = (
        "# Top\n"
        "intro\n"
        "## Child\n"
        "child body\n"
        "# Sibling\n"
        "s\n"
    )
    out = apply_section_op(text, "Top", "replace", "brand new body")
    assert out == (
        "# Top\n"
        "brand new body\n"
        "# Sibling\n"
        "s\n"
    )


def test_apply_section_op_append_after_children():
    text = (
        "# Top\n"
        "intro\n"
        "## Child\n"
        "child body\n"
        "# Sibling\n"
    )
    out = apply_section_op(text, "Top", "append", "appended")
    assert out == (
        "# Top\n"
        "intro\n"
        "## Child\n"
        "child body\n"
        "appended\n"
        "# Sibling\n"
    )


def test_apply_section_op_prepend_after_heading():
    text = "# Top\nintro\n## Child\nc\n"
    out = apply_section_op(text, "Top", "prepend", "new top")
    assert out == "# Top\nnew top\nintro\n## Child\nc\n"


def test_apply_section_op_replace_no_children():
    text = "# Only\nold\n"
    out = apply_section_op(text, "Only", "replace", "new")
    assert out == "# Only\nnew\n"


def test_apply_intro_op_append_no_trailing_newline():
    # File whose last line lacks a trailing newline must not glue onto content.
    text = "# H\n- bullet1"
    out = apply_intro_op(text, "H", "append", "- bullet2")
    assert out == "# H\n- bullet1\n- bullet2\n"


def test_apply_section_op_append_no_trailing_newline():
    text = "# H\n- b1\n## Child\nx"
    out = apply_section_op(text, "H", "append", "- b2")
    assert out == "# H\n- b1\n## Child\nx\n- b2\n"


def test_apply_section_op_cjk_heading():
    text = "# 대시보드\n## 진행 중\n할 일\n### 프로젝트 A\n상세\n"
    out = apply_section_op(text, "대시보드::진행 중", "replace", "새 본문")
    assert "## 진행 중\n새 본문\n" in out
    assert "프로젝트 A" not in out
    assert "# 대시보드" in out


# --------------------------------------------------------------- rename_heading


def test_rename_heading_preserves_level_and_children():
    text = "# Top\n## Old Name\nbody\n### Sub\nx\n"
    out = rename_heading(text, "Top::Old Name", "New Name")
    assert "## New Name\n" in out
    assert "Old Name" not in out
    assert "### Sub\nx\n" in out
    assert "body\n" in out


def test_rename_heading_cjk():
    text = "# 문서\n## 사화 fix\n내용\n"
    out = rename_heading(text, "사화 fix", "사용 fix")
    assert "## 사용 fix\n" in out
    assert "사화" not in out


def test_rename_heading_normalizes_new_title():
    text = "# A\n## B\n"
    out = rename_heading(text, "B", "## C")
    assert "## C\n" in out
    assert "## ## C" not in out


def test_rename_heading_missing_raises():
    try:
        rename_heading("# A\nbody\n", "Nope", "X")
    except ValueError:
        pass
    else:
        assert False, "expected ValueError"


def test_rename_heading_empty_title_raises():
    try:
        rename_heading("# A\n", "A", "##")
    except ValueError:
        pass
    else:
        assert False, "expected ValueError"


# --------------------------------------------------------------- delete_section


def test_delete_section_removes_section_and_descendants():
    text = (
        "# Top\n"
        "intro\n"
        "## A\n"
        "a body\n"
        "### A1\n"
        "x\n"
        "## B\n"
        "b body\n"
    )
    out = delete_section(text, "Top::A")
    assert "## A\n" not in out
    assert "### A1" not in out
    assert "a body" not in out
    assert "## B\nb body\n" in out
    assert "# Top\nintro\n" in out


def test_delete_section_runs_to_eof():
    text = "# Top\n## A\nx\n## Last\ny\n"
    out = delete_section(text, "Last")
    assert "## Last" not in out
    assert out == "# Top\n## A\nx\n"


# --------------------------------------------------------------- heading_level


def test_heading_level():
    text = "# A\n## B\n### C\n"
    assert heading_level(text, "A") == 1
    assert heading_level(text, "A::B") == 2
    assert heading_level(text, "A::B::C") == 3


def test_heading_level_missing_raises():
    try:
        heading_level("# A\n", "B")
    except ValueError:
        pass
    else:
        assert False, "expected ValueError"


# ----------------------------------------------------------- leading_heading_level


def test_leading_heading_level_heading_first():
    assert leading_heading_level("## New\nbody\n") == 2
    assert leading_heading_level("# Title") == 1


def test_leading_heading_level_prose():
    assert leading_heading_level("just text\n## later\n") is None


def test_leading_heading_level_skips_blank():
    assert leading_heading_level("\n\n### Deep\n") == 3


def test_leading_heading_level_empty():
    assert leading_heading_level("") is None
    assert leading_heading_level("\n   \n") is None


if __name__ == "__main__":
    import traceback
    failed = 0
    passed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"[PASS] {name}")
                passed += 1
            except Exception:
                print(f"[FAIL] {name}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
