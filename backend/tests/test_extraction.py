from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.extraction import validate_recognition, extract_with_client


def result(fields=None, kind="case"):
    return {"kind": kind, "title": "表4 比較法調查估價表", "summary": "已辨識表4", "fields": fields or [], "warnings": []}


def field(value="130,167", key="unitPrice", target="comparable-1"):
    return {"target": target, "key": key, "value": value, "source": "工作表：表4 G5", "evidence": f"G5={value}"}


def test_extract_endpoint_returns_fields_with_sources():
    seen = {}
    def extract(document):
        seen.update(document)
        return result([field()])
    client = TestClient(create_app(extractor=extract))
    response = client.post("/api/extract-case", json={"name": "案件.xlsx", "text": "工作表：表4\nG5=130,167", "images": []})
    assert response.status_code == 200
    assert response.json()["fields"][0]["value"] == "130,167"
    assert seen["name"] == "案件.xlsx"


def test_unsupported_values_are_removed_not_invented():
    out = validate_recognition(result([field("999999")]), {"text": "G5=130,167", "images": []})
    assert out["fields"] == []
    assert out["warnings"]


def test_blank_template_does_not_invent_case_numbers_from_headers():
    out = validate_recognition(result([], "template"), {"text": "比較標的1 實例編號： 土地正常單價", "images": []})
    assert out["kind"] == "template"
    assert out["fields"] == []


def test_rejects_invented_evidence_even_if_the_number_occurs_in_a_header():
    value = field("1", key="caseNo")
    value["source"] = "工作表：表4 H2"
    value["evidence"] = 'H2="實例編號：1"'
    out = validate_recognition(result([value]), {"text": 'G2="比較標的1" H2="實例編號："', "images": []})
    assert out["fields"] == []


def test_invalid_target_field_combination_is_not_accepted():
    out = validate_recognition(result([field(target="subject")]), {"text": "G5=130,167", "images": []})
    assert out["fields"] == []


def test_image_page_must_exist_for_ocr_evidence():
    value = field(); value["source"] = "第 2 頁"
    out = validate_recognition(result([value]), {"text": "", "images": [{"page": 1, "data": ""}]})
    assert out["fields"] == []


def test_conflicting_values_are_flagged_without_selecting_either():
    out = validate_recognition(result([field("130,167"), field("135,275")]), {"text": "第1頁 G5=130,167 第2頁 G5=135,275", "images": []})
    assert out["fields"] == []
    assert any("不同值" in warning for warning in out["warnings"])


def test_official_table4_subject_transaction_date_is_the_case_base_date():
    text = '工作表：表4比較法調查估價表\nA1="表4 比較法調查估價表"\tK1="估價基準日："\nD2="比準地：宗地流水號"\nA6="交易日期"\tD6="111年9月1日"'
    out = validate_recognition(result([]), {"text": text, "images": []})
    assert out["fields"] == [{"target": "subject", "key": "baseDate", "value": "111年9月1日", "source": "工作表：表4比較法調查估價表，儲存格 D6", "evidence": 'D6="111年9月1日"'}]


def test_d6_is_not_assumed_to_be_a_base_date_in_other_tables():
    out = validate_recognition(result([]), {"text": '工作表：其他表\nA1="交易紀錄"\nA6="交易日期"\tD6="111年9月1日"', "images": []})
    assert out["fields"] == []


def test_filled_table4_case_numbers_are_values_not_comparable_headers():
    text = '工作表：表4比較法調查估價表\nA1="表4 比較法調查估價表"\nD2="比準地：宗地流水號"\tG2="比較標的1"\tH2="實例編號：1"\tK2="比較標的2"\tL2="實例編號：A-002"\tO2="比較標的3"\tP2="實例編號：3"'
    out = validate_recognition(result([]), {"text": text, "images": []})
    assert [(f["target"], f["key"], f["value"]) for f in out["fields"]] == [
        ("comparable-1", "caseNo", "1"), ("comparable-2", "caseNo", "A-002"), ("comparable-3", "caseNo", "3")]
    assert all('實例編號：' in f["evidence"] for f in out["fields"])


def test_blank_official_table4_does_not_use_comparable_header_numbers():
    text = '工作表：表4比較法調查估價表\nA1="表4 比較法調查估價表"\nD2="比準地：宗地流水號"\tG2="比較標的1"\tH2="實例編號："\tK2="比較標的2"\tL2="實例編號："\tO2="比較標的3"\tP2="實例編號："'
    out = validate_recognition(result([], "template"), {"text": text, "images": []})
    assert out["fields"] == []
    assert out["kind"] == "template"


def test_batches_scan_pages_without_losing_original_page_numbers():
    class Client:
        def __init__(self):
            self.calls = []
        def converse(self, **kwargs):
            self.calls.append(kwargs)
            n = 1 if len(self.calls) == 1 else 6
            value = field(); value["source"] = f"第 {n} 頁"
            return {"output": {"message": {"content": [{"toolUse": {"name": "record_case_fields", "input": result([value])}}]}}}
    client = Client()
    out = extract_with_client(client, "model", {"name": "多頁.pdf", "text": "", "images": [{"page": n, "data": "aGVsbG8="} for n in range(1, 7)]})
    assert len(client.calls) == 2
    assert "第 6 頁" in client.calls[1]["messages"][0]["content"][1]["text"]
    assert len(out["fields"]) == 1


def test_bedrock_uses_forced_structured_tool_and_includes_scan_image():
    class Client:
        def converse(self, **kwargs):
            self.kwargs = kwargs
            return {"output": {"message": {"content": [{"toolUse": {"name": "record_case_fields", "input": result([], "template")}}]}}}
    client = Client()
    out = extract_with_client(client, "model", {"name": "掃描.pdf", "text": "", "images": [{"page": 1, "data": "aGVsbG8="}]})
    assert out["kind"] == "template"
    assert client.kwargs["toolConfig"]["toolChoice"] == {"tool": {"name": "record_case_fields"}}
    blocks = client.kwargs["messages"][0]["content"]
    assert any(block.get("image", {}).get("source", {}).get("bytes") == b"hello" for block in blocks)


def test_model_failure_is_an_error_not_empty_case_success():
    def broken(document):
        raise RuntimeError("unavailable")
    client = TestClient(create_app(extractor=broken))
    response = client.post("/api/extract-case", json={"name": "案件.pdf", "text": "地號", "images": []})
    assert response.status_code == 502
    assert "辨識" in response.json()["detail"]


@pytest.mark.parametrize("payload", [{"name": "a.pdf", "text": "", "images": []}, {"name": "a.pdf", "text": "x" * 80001, "images": []}])
def test_rejects_empty_or_oversized_request(payload):
    client = TestClient(create_app(extractor=lambda d: result()))
    assert client.post("/api/extract-case", json=payload).status_code == 422
