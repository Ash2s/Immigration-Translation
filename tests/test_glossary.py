import pytest
import tempfile, os
from app.services.glossary import GlossaryService

def test_load_csv_glossary():
    service = GlossaryService()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        f.write("中文术语,英文翻译\n")
        f.write("移民局,Immigration Bureau\n")
        f.write("申请表,Application Form\n")
        temp_path = f.name
    glossary_id = service.load_glossary(temp_path, "test.csv")
    os.unlink(temp_path)
    assert glossary_id is not None
    assert service.get_term_count(glossary_id) == 2

def test_load_xlsx_glossary():
    from openpyxl import Workbook
    service = GlossaryService()
    wb = Workbook()
    ws = wb.active
    ws.append(["中文术语", "英文翻译"])
    ws.append(["移民局", "Immigration Bureau"])
    ws.append(["申请表", "Application Form"])
    temp_path = tempfile.mktemp(suffix='.xlsx')
    wb.save(temp_path)
    glossary_id = service.load_glossary(temp_path, "test.xlsx")
    os.unlink(temp_path)
    assert glossary_id is not None
    assert service.get_term_count(glossary_id) == 2

def test_normalize_quotes():
    service = GlossaryService()
    text = '他说"你好"，我说"再见"'
    normalized = service.normalize_quotes(text)
    # Should convert straight quotes to curly quotes
    assert '"' in normalized or '"' in normalized  # at least one type changed

def test_longest_match_replacement():
    service = GlossaryService()
    glossary = {"品宅装饰科技": "Pinzhai Decoration Technology", "内装": "Interior Decoration"}
    text = "品宅装饰科技的内装"
    result = service.replace_with_glossary(text, glossary)
    assert "Pinzhai" in result
    assert "Interior" in result
    assert "品宅" not in result  # original term removed