"""Tests for the TranslatorService."""

from unittest.mock import patch, MagicMock
from app.services.translator import TranslatorService


def test_longest_match_replacement():
    """Longest glossary key should be matched before shorter ones."""
    service = TranslatorService()
    glossary = {
        "品宅装饰科技": "Pinzhai Decoration Technology",
        "内装": "Interior Decoration",
    }
    text = "品宅装饰科技的内装"
    result = service.replace_with_glossary(text, glossary)
    assert "Pinzhai" in result
    assert "Interior" in result
    # The original Chinese should be fully replaced
    assert "品宅" not in result
    assert "内装" not in result


def test_detect_chinese_residue():
    """Detect remaining Chinese characters in text."""
    service = TranslatorService()

    # Text with Chinese characters
    result = service.detect_chinese_residue("Hello世界")
    assert "世" in result
    assert "界" in result

    # Text without Chinese characters
    result = service.detect_chinese_residue("Hello World")
    assert result == []

    # Empty text
    result = service.detect_chinese_residue("")
    assert result == []


def test_fix_cn_labels():
    """Chinese labels should be replaced with English equivalents."""
    service = TranslatorService()

    assert service.fix_cn_labels("【图片】") == "[Image]"
    assert service.fix_cn_labels("【条形码】") == "[Barcode]"
    assert service.fix_cn_labels("【盖章】") == "[Seal]"

    # Mixed content
    assert "【图片】" not in service.fix_cn_labels("See 【图片】 below")
    assert "[Image]" in service.fix_cn_labels("See 【图片】 below")

    # Text without labels should remain unchanged
    assert service.fix_cn_labels("Normal text") == "Normal text"


def test_convert_chinese_dates():
    """Chinese date expressions should be converted to English format."""
    service = TranslatorService()

    # Full date
    assert service.convert_chinese_dates("2025年10月22日") == "October 22, 2025"
    # Year + month (no day)
    assert service.convert_chinese_dates("2025年10月") == "October 2025"
    # Month + day (no year)
    assert service.convert_chinese_dates("10月22日") == "October 22"
    # Single-digit month/day
    assert service.convert_chinese_dates("2024年3月5日") == "March 5, 2024"
    assert service.convert_chinese_dates("3月5日") == "March 5"
    # Date embedded in sentence
    assert "June 1, 2024" in service.convert_chinese_dates("于2024年6月1日生效")
    # No date present — unchanged
    assert service.convert_chinese_dates("普通文本") == "普通文本"
    assert service.convert_chinese_dates("Hello World") == "Hello World"
    # Empty
    assert service.convert_chinese_dates("") == ""


def test_translate_text_mocked():
    """Translate text with a mocked OpenAI client."""
    service = TranslatorService()
    test_text = "你好世界"
    glossary = {"你好": "Hello"}

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Hello World"))
    ]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch.object(service, "_make_client", return_value=mock_client):
        result = service.translate_text(test_text, glossary)

    assert result == "Hello World"
    # Verify the API was called with correct params
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "deepseek-v4-flash"
    assert call_kwargs["temperature"] == 0.3
    assert len(call_kwargs["messages"]) == 2  # system + user


def test_translate_text_api_error():
    """API errors should be handled gracefully without crashing."""
    service = TranslatorService()
    test_text = "你好世界"
    glossary = {"你好": "Hello"}

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API Error")

    with patch.object(service, "_make_client", return_value=mock_client):
        result = service.translate_text(test_text, glossary)

    # Should return original text with error prefix
    assert "[Translation Error]" in result
    assert test_text in result


def test_polish_text_returns_polished_text():
    """polish_text should send text through the API with a proofreading prompt."""
    service = TranslatorService()
    input_text = "This project was started in 2024. It is very important."

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="This project commenced in 2024 and holds significant importance."))
    ]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch.object(service, "_make_client", return_value=mock_client):
        result = service.polish_text(input_text)

    assert result == "This project commenced in 2024 and holds significant importance."
    mock_client.chat.completions.create.assert_called_once()


def test_polish_text_returns_original_on_short():
    """polish_text should return original when text is too short."""
    service = TranslatorService()

    assert service.polish_text("") == ""
    assert service.polish_text("Hi") == "Hi"  # 2 chars, below threshold
    # NOTE: Polish text shortened from 20→10 char minimum


def test_polish_text_returns_original_on_api_error():
    """polish_text should fall back to original text on API failure."""
    service = TranslatorService()
    input_text = "More than twenty characters of sample text for testing."

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API Error")

    with patch.object(service, "_make_client", return_value=mock_client):
        result = service.polish_text(input_text)

    assert result == input_text


def test_clean_mechanical_errors():
    """Pre-clean should fix repeated words, missing spaces, and other mechanical errors."""
    # Duplicated word (two spaces between)
    assert "indoor temperature" in TranslatorService._clean_mechanical_errors(
        "the indoor  indoor temperature"
    )
    # Missing space: lowercase→uppercase
    result = TranslatorService._clean_mechanical_errors("Northeast regionRelatively prominent")
    assert "region Relatively" in result
    # 3+ consecutive identical chars → reduced to 1
    assert "mispelled" in TranslatorService._clean_mechanical_errors("missspelled word")
    # Punctuation without space: "climate.trend" → "climate. trend"
    assert "climate. trend" in TranslatorService._clean_mechanical_errors("climate.trend")
    # Parenthesis merging: "PMV(Predicted" → "PMV (Predicted"
    result = TranslatorService._clean_mechanical_errors("asPMV(Predicted Mean")
    assert "PMV (Predicted" in result
    # Apostrophe merging: "Germany'sFraunhofer" → "Germany's Fraunhofer"
    result = TranslatorService._clean_mechanical_errors("Germany'sFraunhofer Institute")
    assert "Germany's Fraunhofer" in result
    # Duplicated phrase
    assert "has gradually become" in TranslatorService._clean_mechanical_errors(
        "gradually has gradually become"
    )
    # No false positives
    assert TranslatorService._clean_mechanical_errors("Hello World") == "Hello World"
    assert "committee" in TranslatorService._clean_mechanical_errors("committee")
