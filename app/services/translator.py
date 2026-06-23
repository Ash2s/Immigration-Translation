"""Translator service for calling DeepSeek API to translate Chinese to English."""

import re
import httpx
from datetime import datetime
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

# ---------------------------------------------------------------------------
# Chinese date patterns — convert to English before translation so the model
# never sees 年/月/日 as standalone words.
# ---------------------------------------------------------------------------
MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]

# Full date    2025年10月22日  →  October 22, 2025
# Year+month   2025年10月     →  October 2025
# Month+day    10月22日       →  October 22
_CHINESE_FULL_DATE_RE = re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')
_CHINESE_YEAR_MONTH_RE = re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月(?!\s*\d)')
_CHINESE_MONTH_DAY_RE = re.compile(r'(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日')


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

        # Convert Chinese dates to English format before glossary replacement,
        # so year/month/day are never treated as standalone translatable words.
        text = self.convert_chinese_dates(text)

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

        # Convert Chinese dates to English format BEFORE sending to API,
        # so the model never sees 年/月/日 as standalone words.
        processed_text = self.convert_chinese_dates(text)

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
                "IMPORTANT — Date translation rules:\n"
                "- Chinese dates like X年X月X日 must be translated as a whole into natural English date format.\n"
                "  Example: 2025年10月22日 → October 22, 2025 (NOT \"2025 October 22\" or \"22 October 2025 Year\")\n"
                "- 年/月/日 are date components, NOT standalone words. Never translate them as \"year/month/days\".\n"
                "- Use the standard American English date format: Month Day, Year (e.g. March 15, 2024).\n"
                "- If only year+month (X年X月), write as \"October 2025\".\n"
                "- If only month+day (X月X日), write as \"October 22\".\n"
                "Use Times New Roman style, formal tone, and double line spacing.\n"
                "Output only the translated text, no explanations."
            )

        try:
            response = client.chat.completions.create(
                model=active_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": processed_text},
                ],
                temperature=temperature if temperature is not None else 0.3,
            )
            translated = response.choices[0].message.content
            return translated.strip() if translated else text
        except Exception as e:
            return f"[Translation Error]: {text}"

    # ------------------------------------------------------------------
    # English polishing — post-translation quality pass
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_mechanical_errors(text: str) -> str:
        """Fix deterministic mechanical errors: duplicated chars/words,
        missing spaces at word boundaries, punctuation, parentheses.

        Applied to ALL translated text (both full-paragraph and per-run)
        regardless of whether the polish step runs."""
        if not text:
            return text
        # 3+ consecutive identical chars (clear typo: "missspelled"→"mispelled")
        result = re.sub(r'(\w)\1{2,}', r'\1', text)
        # Duplicated whole word: "the the" or "has gradually has gradually"
        result = re.sub(r'\b(\w+)\s+\1\b', r'\1', result)
        # lowercase→UPPERCASE word boundary: "regionRelatively" → "region Relatively"
        result = re.sub(r'([a-z])([A-Z])', r'\1 \2', result)
        # Punctuation without trailing space: "climate.trend" → "climate. trend"
        result = re.sub(r'([.,;:!?])([A-Za-z])', r'\1 \2', result)
        # Word before opening paren: "PMV(Predicted" → "PMV (Predicted"
        result = re.sub(r'(\w)\(', r'\1 (', result)
        # Closing paren before word: "system)such" → "system) such"
        result = re.sub(r'\)(\w)', r') \1', result)
        # Apostrophe-s merging: "Germany'sFraunhofer" → "Germany's Fraunhofer"
        result = re.sub(r"([a-zA-Z])'s([A-Z])", r"\1's \2", result)
        # Double spaces
        result = re.sub(r' {2,}', ' ', result)
        return result

    def polish_text(
        self,
        text: str,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> str:
        """
        Polish English *text* to read like natural, fluent academic English.

        Applies a deterministic pre-clean pass for mechanical errors (duplicated
        letters, repeated words, missing word-boundary spaces), then sends the
        text through the API with a proofreading system prompt that focuses on
        grammar, flow, word choice, and removal of translationese ("Chinglish").
        A final post-clean pass catches any residual mechanical issues.

        Parameters
        ----------
        text : str
            English text to polish / proofread.
        api_key, base_url, model : str | None
            Custom API credentials.  If omitted, uses the server defaults.

        Returns
        -------
        str
            Polished English text.  On API failure, returns the pre-cleaned
            *text*.
        """
        if not text or len(text) < 10:
            return text

        # ── Pre-clean mechanical errors ──
        pre_cleaned = self._clean_mechanical_errors(text)

        client = self._make_client(api_key, base_url)
        active_model = model or self._model

        system_prompt = (
            "You are a professional English proofreader for academic and immigration documents. "
            "Revise the following English text so it reads like natural, fluent, academic-level English "
            "written by a native speaker.\n\n"
            "CRITICAL — fix these specific issues:\n"
            "- Typographical errors: duplicated letters (e.g. \"decdecision\"→\"decision\") "
            "or truncated words (e.g. \"Massachu\"→\"Massachusetts\").\n"
            "- Duplicate / repeated words (e.g. \"indoor indoor\"→\"indoor\").\n"
            "- Run-together words with missing spaces (e.g. \"regionRelatively\"→\"region relatively\").\n"
            "- Grammar errors: subject-verb agreement, missing articles, incorrect prepositions, "
            "tense consistency.\n"
            "- Chinglish / translationese: unnatural word order, calques from Chinese, "
            "overly literal phrasing. Rewrite to sound like natural academic English.\n"
            "- Improve sentence flow: split run-on sentences, merge short choppy ones, add "
            "appropriate transitions.\n\n"
            "RULES:\n"
            "- Maintain a formal academic tone throughout.\n"
            "- Preserve ALL [bracketed markers] like [Seal], [Image], [Barcode] exactly.\n"
            "- Preserve all numbers, dates, proper nouns, and technical terms exactly.\n"
            "- Do NOT change or remove any factual information — only improve how it is expressed.\n"
            "- If the text contains truncated or clearly malformed words, use context to infer "
            "and restore the correct word.\n"
            "- Output ONLY the revised text, no explanations or commentary."
        )

        try:
            response = client.chat.completions.create(
                model=active_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": pre_cleaned},
                ],
                temperature=0.2,
            )
            polished = response.choices[0].message.content
            result = polished.strip() if polished else pre_cleaned
        except Exception as e:
            result = pre_cleaned

        # ── Post-clean: catch anything the model missed ──
        result = self._clean_mechanical_errors(result)
        return result

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

    @staticmethod
    def convert_chinese_dates(text: str) -> str:
        """Convert Chinese date expressions to English format.

        Handles three patterns:
          - 2025年10月22日  →  October 22, 2025
          - 2025年10月     →  October 2025  (standalone year+month)
          - 10月22日       →  October 22    (standalone month+day)

        Also handles a comma before 日 for edge cases like 2025年10月22日,
        Parameters
        ----------
        text : str
            Text possibly containing Chinese date expressions.

        Returns
        -------
        str
            Text with dates converted to English format.
        """
        def _full_date(m: re.Match) -> str:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f"{MONTH_NAMES[mo]} {d}, {y}"

        def _year_month(m: re.Match) -> str:
            y, mo = int(m.group(1)), int(m.group(2))
            return f"{MONTH_NAMES[mo]} {y}"

        def _month_day(m: re.Match) -> str:
            mo, d = int(m.group(1)), int(m.group(2))
            return f"{MONTH_NAMES[mo]} {d}"

        result = _CHINESE_FULL_DATE_RE.sub(_full_date, text)
        result = _CHINESE_YEAR_MONTH_RE.sub(_year_month, result)
        result = _CHINESE_MONTH_DAY_RE.sub(_month_day, result)

        # Also handle the translated string 年/月/日 as standalone words
        # (catch what the model might produce even after conversion)
        result = result.replace('年 ', ' ').replace('月 ', ' ').replace('日 ', ' ')
        return result
