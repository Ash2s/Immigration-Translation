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


def test_translate_text_mocked():
    """Translate text with a mocked OpenAI client."""
    service = TranslatorService()
    test_text = "你好世界"
    glossary = {"你好": "Hello"}

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Hello World"))
    ]

    with patch.object(service, "_client") as mock_client:
        mock_client.chat.completions.create.return_value = mock_response
        result = service.translate_text(test_text, glossary)

    assert result == "Hello World"
    # Verify the API was called with correct params
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "deepseek-chat"
    assert call_kwargs["temperature"] == 0.3
    assert len(call_kwargs["messages"]) == 2  # system + user


def test_translate_text_api_error():
    """API errors should be handled gracefully without crashing."""
    service = TranslatorService()
    test_text = "你好世界"
    glossary = {"你好": "Hello"}

    with patch.object(service, "_client") as mock_client:
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        result = service.translate_text(test_text, glossary)

    # Should return original text with error prefix
    assert "[Translation Error]" in result
    assert test_text in result
