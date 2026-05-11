"""Translator service for calling DeepSeek API to translate Chinese to English."""

import re
import httpx
from openai import OpenAI
from app.config import settings


class TranslatorService:
    """
    Service for translating Chinese immigration document text to English
    via the DeepSeek API (OpenAI-compatible endpoint).

    Provides glossary-aware replacement, Chinese residue detection, and
    Chinese label cleanup utilities.
    """

    def __init__(self):
        """Initialise the OpenAI client with DeepSeek credentials."""
        # Pass an explicit http_client to avoid httpx 0.28+ proxies compatibility issue
        self._client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
            http_client=httpx.Client(),
        )
        self._model = settings.DEEPSEEK_MODEL

    # ------------------------------------------------------------------
    # Glossary-aware replacement
    # ------------------------------------------------------------------

    def replace_with_glossary(self, text: str, glossary: dict[str, str]) -> str:
        """
        Replace Chinese terms in *text* using *glossary* with longest-match-first
        strategy so that longer terms are matched before overlapping shorter ones.

        Parameters
        ----------
        text : str
            The text to process.
        glossary : dict[str, str]
            Mapping of Chinese term -> English translation.

        Returns
        -------
        str
            Text with glossary terms replaced.
        """
        if not text or not glossary:
            return text

        # Sort by key length descending so longer terms are replaced first
        sorted_terms = sorted(glossary.keys(), key=len, reverse=True)

        result = text
        for term in sorted_terms:
            pattern = re.escape(term)
            result = re.sub(pattern, glossary[term], result)

        return result

    # ------------------------------------------------------------------
    # DeepSeek API translation
    # ------------------------------------------------------------------

    def translate_text(self, text: str, glossary: dict[str, str]) -> str:
        """
        Translate Chinese *text* to English via the DeepSeek API.

        The *glossary* is injected into the system prompt to ensure technical
        terms are translated consistently.

        Parameters
        ----------
        text : str
            Chinese text to translate.
        glossary : dict[str, str]
            Mapping of Chinese term -> English translation.

        Returns
        -------
        str
            Translated English text. If the API call fails, returns the
            original text prefixed with ``[Translation Error]: ``.
        """
        glossary_lines = "\n".join(
            f"{cn} → {en}" for cn, en in glossary.items()
        )

        system_prompt = (
            "You are a professional immigration document translator. "
            "Translate the following Chinese text to English accurately and formally.\n"
            "Use the provided glossary for technical terms:\n"
            f"{glossary_lines}\n\n"
            "Preserve formatting markers such as (Seal), (Signature), [Image], [Barcode].\n"
            "Use Times New Roman style, formal tone, and double line spacing.\n"
            "Output only the translated text, no explanations."
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.3,
            )
            translated = response.choices[0].message.content
            return translated.strip() if translated else text
        except Exception as e:
            return f"[Translation Error]: {text}"

    # ------------------------------------------------------------------
    # Quality-assurance helpers
    # ------------------------------------------------------------------

    @staticmethod
    def detect_chinese_residue(text: str) -> list[str]:
        """
        Scan *text* and return a list of any remaining Chinese characters
        found (using the Unicode CJK Unified Ideographs block).

        Parameters
        ----------
        text : str
            Text to scan.

        Returns
        -------
        list[str]
            List of individual Chinese characters found (empty if none).
        """
        return re.findall(r"[一-鿿]", text)

    @staticmethod
    def fix_cn_labels(text: str) -> str:
        """
        Replace common Chinese formatting labels with their English equivalents.

        ============= ===========
        Chinese label English
        ============= ===========
        ``【图片】``   ``[Image]``
        ``【条形码】`` ``[Barcode]``
        ``【盖章】``   ``[Seal]``
        ============= ===========

        Parameters
        ----------
        text : str
            Text containing Chinese labels.

        Returns
        -------
        str
            Text with labels replaced.
        """
        replacements = {
            "【图片】": "[Image]",
            "【条形码】": "[Barcode]",
            "【盖章】": "[Seal]",
        }
        result = text
        for cn, en in replacements.items():
            result = result.replace(cn, en)
        return result
