from unittest.mock import MagicMock, patch

import pytest

from cloudflare_executive_report.ai.client import call_llm
from cloudflare_executive_report.ai.formatter import format_portfolio_as_text
from cloudflare_executive_report.ai.summary import generate_ai_summary
from cloudflare_executive_report.config import AiSummaryConfig
from cloudflare_executive_report.executive.portfolio import (
    PortfolioRiskRow,
    PortfolioSummary,
    PortfolioZoneRow,
)


@pytest.fixture
def mock_portfolio() -> PortfolioSummary:
    return PortfolioSummary(
        zones=[
            PortfolioZoneRow(
                zone_name="test.com",
                security_score=85.0,
                security_grade="A",
                critical_risks=1,
                warning_risks=2,
            ),
            PortfolioZoneRow(
                zone_name="example.com",
                security_score=50.0,
                security_grade="D+",
                critical_risks=3,
                warning_risks=1,
            ),
        ],
        common_risks=[
            PortfolioRiskRow(
                phrase_key="waf_disabled",
                phrase_text="WAF is disabled",
                check_id="sec_waf",
                zone_count=2,
            ),
        ],
        grade_distribution={"A": 1, "D+": 1},
        zones_sort_caption="score asc",
    )


@pytest.fixture
def mock_config() -> AiSummaryConfig:
    return AiSummaryConfig(
        enabled=True,
        model="test-model",
        api_key="test-key",
    )


def test_format_portfolio_as_text(mock_portfolio: PortfolioSummary) -> None:
    text = format_portfolio_as_text(mock_portfolio)
    assert "Total zones evaluated: 2" in text
    assert "A (85-94): 1 zone" in text
    assert "D+ (45-54): 1 zone" in text
    assert "- WAF is disabled (sec_waf): 2 zones" in text
    # Ensure zone names are NOT in the text
    assert "test.com" not in text
    assert "example.com" not in text


@patch("cloudflare_executive_report.ai.client._get_litellm")
def test_call_llm_success(mock_get_litellm: MagicMock) -> None:
    mock_litellm = MagicMock()
    mock_get_litellm.return_value = mock_litellm

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Test summary output"
    mock_litellm.completion.return_value = mock_response

    messages = [{"role": "user", "content": "Input text"}]
    result = call_llm(
        messages,
        model="test-model",
        max_tokens=100,
        temperature=0.3,
        timeout=30,
        api_key="test-key",
    )

    assert result == "Test summary output"
    mock_litellm.completion.assert_called_once()
    kwargs = mock_litellm.completion.call_args.kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["api_key"] == "test-key"


@patch("cloudflare_executive_report.ai.summary.call_llm")
def test_generate_ai_summary_fallback(
    mock_call_llm: MagicMock, mock_portfolio: PortfolioSummary, mock_config: AiSummaryConfig
) -> None:
    mock_config.fallback_models = ["fallback-model"]

    # First call fails (None), second succeeds
    mock_call_llm.side_effect = [None, "Fallback output"]

    result = generate_ai_summary(mock_portfolio, mock_config)

    assert result == "Fallback output"
    assert mock_call_llm.call_count == 2


def test_generate_ai_summary_disabled(
    mock_portfolio: PortfolioSummary, mock_config: AiSummaryConfig
) -> None:
    mock_config.enabled = False
    assert generate_ai_summary(mock_portfolio, mock_config) is None
