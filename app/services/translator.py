"""Translator service for calling DeepSeek API to translate Chinese to English."""

import re
import httpx
from openai import OpenAI
from app.config import settings

# ---------------------------------------------------------------------------
# Common proper nouns used as fallback when user glossary doesn't cover them
# ---------------------------------------------------------------------------
COMMON_TERMS = {
    '中海地产': 'China Overseas Land & Investment (COOP)',
    '万科地产': 'Vanke Real Estate',
    '景瑞控股': 'Jingrui Holdings',
    '华润': 'China Resources',
    '百安居': 'B&Q',
    '旭辉': 'Xuhui Group',
    '招商': 'China Merchants',
    '上海地产': 'Shanghai Land',
    '首旅如家': 'BTU Ruijia',
    '锦江': 'Jinjiang Hotels',
    '华住': 'Huazhu Hotels',
    '格林': 'GreenTree Hotels',
    '恒大': 'Evergrande',
    '万科': 'Vanke',
    '清华': 'Tsinghua University',
    '长安大学': "Chang'an University",
    '中欧国际商学院': 'China Europe International Business School (CEIBS)',
    '香港技术研究院': 'Hong Kong Institute of Technology',
    '中国智慧工程研究会': 'China Society of Intelligent Engineering',
    '创意空间杯': 'Creative Space Cup',
    '建筑声学': 'architectural acoustics',
    '数字化转型': 'digital transformation',
    '双碳': '"dual carbon"',
    '碳达峰': 'carbon peak',
    '碳中和': 'carbon neutrality',
    '智慧城市': 'smart city',
    '零碳建筑': 'zero-carbon buildings',
    '装配式内装': 'prefabricated interior decoration',
    '工业化': 'industrialization',
    '内装工业化': 'interior industrialization',
    '数字化': 'digitalization',
    '数字化工具': 'digital tools',
    '生物气候建筑': 'bioclimatic architecture',
    '室内热舒适性': 'indoor thermal comfort',
    '拓扑算法': 'topological algorithms',
    '空间句法': 'spatial syntax',
    '绿色决策支持系统': 'green decision-support system',
    '系统架构师': 'technical architect',
    '绿色建材': 'green building materials',
    '装修': 'decoration',
    '精装': 'finished interior',
    '装配式建筑': 'prefabricated building',
    '全装修': 'full-decoration',
    'SI体系': 'SI structural system',
    '现场湿作业': 'on-site wet work',
    '无醛无毒': 'formaldehyde-free and non-toxic',
    '资源回收再利用': 'recycling and reuse',
    '装修垃圾': 'decoration waste',
    '部品': 'components',
    '首席执行官': 'Chief Executive Officer',
    '云平台': 'Cloud Platform',
    '注册建筑师': 'Registered Architect',
    '国家高新技术企业': 'National High-Tech Enterprise',
    '参编': 'participated in drafting',
    '主编': 'editor-in-chief',
    '第一负责人': 'Principal Investigator',
    '联合创始人': 'Co-Founder',
    '核心合伙人': 'Core Partner',
    '客座教授': 'Visiting Professor',
    '特聘专家': 'Distinguished Expert',
    '评审专家': 'Review Expert',
    '副研究员': 'Associate Researcher',
    '卡瑞': 'CARR',
}


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
            http_client=httpx.Client(
                transport=httpx.HTTPTransport(),
                timeout=httpx.Timeout(60.0, connect=10.0),
            ),
        )
        self._model = settings.DEEPSEEK_MODEL

    # ------------------------------------------------------------------
    # Glossary-aware replacement
    # ------------------------------------------------------------------

    def replace_with_glossary(self, text: str, glossary: dict[str, str]) -> str:
        """
        Replace Chinese terms in *text* using longest-match-first strategy.

        Merges COMMON_TERMS as fallback (user glossary takes priority).
        Also performs space-normalized fuzzy matching so that glossary keys
        with spaces match text where spaces were omitted (e.g. "系统 V1.0"
        matches "系统V1.0").

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
        if not text:
            return text

        # Merge with COMMON_TERMS fallback (user glossary takes priority)
        merged = dict(COMMON_TERMS)
        merged.update(glossary)
        if not merged:
            return text

        # Add space-normalized versions for fuzzy matching
        extended = dict(merged)
        for cn, en in merged.items():
            norm = cn.replace(' ', '').replace('　', '')
            if norm != cn and norm not in extended:
                extended[norm] = en

        # Sort by key length descending (longest match first)
        sorted_terms = sorted(extended.keys(), key=len, reverse=True)

        result = text
        for term in sorted_terms:
            pattern = re.escape(term)
            result = re.sub(pattern, extended[term], result)

        return result

    # ------------------------------------------------------------------
    # DeepSeek API translation
    # ------------------------------------------------------------------

    def _make_client(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> OpenAI:
        """Create an OpenAI client (always fresh for thread safety)."""
        return OpenAI(
            api_key=api_key or settings.DEEPSEEK_API_KEY,
            base_url=base_url or "https://api.deepseek.com",
            http_client=httpx.Client(
                transport=httpx.HTTPTransport(),
                timeout=httpx.Timeout(60.0, connect=10.0),
            ),
        )

    def translate_text(
        self,
        text: str,
        glossary: dict[str, str],
        system_override: str | None = None,
        temperature: float | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> str:
        """
        Translate Chinese *text* to English via the API.

        The *glossary* is injected into the system prompt to ensure technical
        terms are translated consistently.

        Parameters
        ----------
        text : str
            Chinese text to translate.
        glossary : dict[str, str]
            Mapping of Chinese term -> English translation.
        system_override : str | None
            If provided, use this instead of the default translation system prompt.
        temperature : float | None
            Model temperature override.  Defaults to 0.3 if not specified.
        api_key, base_url, model : str | None
            Custom API credentials. If omitted, uses the server defaults.

        Returns
        -------
        str
            Translated English text. If the API call fails, returns the
            original text prefixed with ``[Translation Error]: ``.
        """
        client = self._make_client(api_key, base_url)
        active_model = model or self._model

        combined = dict(COMMON_TERMS)
        combined.update(glossary)
        glossary_lines = "\n".join(
            f"{cn} → {en}" for cn, en in combined.items()
        )

        if system_override is not None:
            system_prompt = system_override
        else:
            system_prompt = (
                "You are a professional immigration document translator. "
                "Translate the following Chinese text to English accurately and formally.\n"
                "Use the provided glossary for technical terms:\n"
                f"{glossary_lines}\n\n"
                "Preserve formatting markers such as (Seal), (Signature), [Image], [Barcode].\n"
                "Convert Chinese numbered lists (一、二、三… / 第一、第二、第三… / 1、2、3… / (一)(二)…) "
                "to English format (I. II. III. / 1. 2. 3. / (1) (2)…).\n"
                "Use Times New Roman style, formal tone, and double line spacing.\n"
                "Output only the translated text, no explanations."
            )

        try:
            response = client.chat.completions.create(
                model=active_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=temperature if temperature is not None else 0.3,
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

    # ------------------------------------------------------------------
    # Formatting feedback interpretation
    # ------------------------------------------------------------------

    def interpret_formatting_feedback(
        self,
        feedback: str,
        paragraphs_text: list[str],
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> dict:
        """Use the model to interpret formatting feedback and identify target paragraphs.

        Sends the full list of paragraph texts + the user's formatting request to
        the model, and returns a structured dict describing which paragraphs to
        modify and how.

        Parameters
        ----------
        feedback : str
            The user's formatting request (e.g. "将结尾的签名改为红色").
        paragraphs_text : list[str]
            All paragraph texts in the document (for context).

        Returns
        -------
        dict
            A dict with:
            - ``needs_retranslation`` (bool): whether content re-translation is also needed
            - ``actions`` (list[dict]): each dict has ``indices`` (list[int]), ``action`` (str),
              and ``value`` (str).  ``indices`` may be empty meaning "all paragraphs".
        """
        # Build a compact paragraph listing
        para_lines = []
        for i, t in enumerate(paragraphs_text):
            preview = t[:60].replace('\n', ' ')
            para_lines.append(f"  [{i}] {preview}")
        para_block = "\n".join(para_lines)

        system_prompt = (
            "You are a document formatting assistant. Given a list of paragraph texts "
            "and a user's formatting request, identify which paragraphs should be "
            "modified and what formatting to apply.\n\n"
            "Return ONLY valid JSON in this exact format:\n"
            "{\n"
            '  "needs_retranslation": false,\n'
            '  "actions": [\n'
            '    {\n'
            '      "indices": [0, 1, 2],\n'
            '      "action": "font_color",\n'
            '      "value": "FF0000"\n'
            '    }\n'
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- If the user asks about content changes, set needs_retranslation to true.\n"
            "- If formatting-only (e.g. \"make red\", \"change font\"), set needs_retranslation to false.\n"
            '- Possible actions: "font_color" (hex value), "line_spacing" ("single"/"double"/"1.5"), '
            '"bold" (true/false), "italic" (true/false), "font_name" (string).\n'
            "- If the request targets specific paragraphs (e.g. \"signature\", \"title\", \"结尾\"), "
            "list their indices.  If it targets the whole document, omit indices (empty array).\n"
            "- Use only the paragraph indices from the listing above.\n"
            "- If the request is ambiguous, target all paragraphs."
        )

        user_prompt = (
            f"Paragraphs:\n{para_block}\n\n"
            f"Formatting request: {feedback}"
        )

        try:
            raw = self.translate_text(
                user_prompt,
                glossary={},
                system_override=system_prompt,
                temperature=0.1,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
            # Extract JSON from the response
            import json
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                if "actions" not in result:
                    result["actions"] = []
                if "needs_retranslation" not in result:
                    result["needs_retranslation"] = False
                return result
        except Exception:
            pass

        # Fallback: empty result (no formatting)
        return {"needs_retranslation": False, "actions": []}

    @staticmethod
    def _cn_numeral(n: int) -> str:
        """Return Chinese numeral *n* (1-10) as the character."""
        return ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十'][n - 1]

    @staticmethod
    def _roman_numeral(n: int) -> str:
        """Return Roman numeral for *n* (1-10)."""
        return ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'][n - 1]

    @staticmethod
    def _build_cn_enum_pattern() -> list[tuple[re.Pattern, str]]:
        """Build regex patterns for Chinese enumeration markers.

        Returns a list of ``(compiled_regex, replacement_template)`` tuples.
        """
        patterns = []
        for i in range(1, 11):
            cn = TranslatorService._cn_numeral(i)
            roman = TranslatorService._roman_numeral(i)
            # Line-start: "一、" → "I."
            patterns.append((
                re.compile(rf'(?<![^\s]){re.escape(cn)}、'),
                f'{roman}.',
            ))
            # Ordinal prefix: "第一、" → "I."
            patterns.append((
                re.compile(rf'(?<![^\s])第{re.escape(cn)}、'),
                f'{roman}.',
            ))
            # Parenthesized halfwidth: "(一)" → "(I)"
            patterns.append((
                re.compile(rf'\(({re.escape(cn)})\)'),
                rf'({roman})',
            ))
            # Parenthesized fullwidth: "（一）" → "(I)"
            patterns.append((
                re.compile(rf'（{re.escape(cn)}）'),
                rf'({roman})',
            ))

        # Arabic numeral with Chinese enumeration comma: "1、" → "1."
        for i in range(0, 10):
            patterns.append((
                re.compile(rf'(?<![^\s]){i}、'),
                f'{i}.',
            ))
        return patterns

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

        Also converts Chinese enumeration markers (一、二、三… → I. II. III.)
        as a post-processing fallback for any the model missed.

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
            "【图标】": "[Logo]",
            "【盖章】": "[Seal]",
            "【英文材料无需翻译】": "[No Translation Required — Source Material in English]",
        }
        result = text
        for cn, en in replacements.items():
            result = result.replace(cn, en)

        # Chinese enumeration fallback
        for pattern, replacement in TranslatorService._build_cn_enum_pattern():
            result = pattern.sub(replacement, result)

        return result
