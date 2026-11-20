"""An anchor repair improves the primary count while a fallback loss stays put."""
from conftest import read_part, repack
from test_fix import DOCX_MCP
from test_repeated_comment_markers import DOC, _before_section, _text_box

from ooxml_integrity import compare
from ooxml_integrity.fix import EXIT_REPAIRED, fix


def test_repair_proves_the_primary_style_count_against_both_text_box_copies(tmp_path):
    def styled(text):
        return f'<w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr><w:t>{text}</w:t></w:r>'

    # Both copies show the same word. The capture already has seven styled
    # runs, so the source has nine in the primary view and nine in the fallback.
    box = _text_box("<w:p>" + styled("Copy") + styled("right") + "</w:p>",
                    "<w:p>" + "".join(styled(c) for c in "Copyright") + "</w:p>")
    source = repack(DOCX_MCP, tmp_path / "source.docx",
                    {DOC: _before_section(read_part(DOCX_MCP, DOC), box)})

    def style_counts(edited):
        return {f.extra.get("branch", "primary"): (f.extra["before"], f.extra["after"])
                for f in compare(source, edited) if f.code == "FID001" and f.extra["tag"] == "rStyle"}

    assert style_counts(DOCX_MCP) == {"primary": (9, 7), "fallback": (9, 0)}
    output = tmp_path / "fixed.docx"
    report = fix(DOCX_MCP, output, against=source)
    assert report.exit_code == EXIT_REPAIRED and report.verification.passed
    assert report.verification.against_added == []
    assert style_counts(output) == {"primary": (9, 8), "fallback": (9, 0)}
