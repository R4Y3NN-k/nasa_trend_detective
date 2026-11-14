# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Stats tests (B replaces these in step 2). Offline."""
from td import analyze, report, sample, trendmap


def test_stats_and_content_contracts_exist():
    for name in ("anomalies", "analyze", "verdict", "correlate", "compare", "agreement"):
        assert callable(getattr(analyze, name))
    assert callable(trendmap.trend_grid)
    assert callable(sample.sample_series) and callable(sample.sample_box_data)
    assert callable(report.markdown_report) and callable(report.csv_bytes)
