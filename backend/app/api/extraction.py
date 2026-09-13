from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.extraction import validate_recognition

router = APIRouter(prefix="/api")


class PageImage(BaseModel):
    page: int = Field(ge=1, le=50)
    data: str = Field(min_length=1, max_length=2_000_000, pattern=r"^[A-Za-z0-9+/]*={0,2}$")


class DocumentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    text: str = Field(default="", max_length=80_000)
    images: list[PageImage] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.text.strip() and not self.images:
            raise ValueError("文件沒有可辨識的文字或頁面")
        return self


@router.post("/extract-case")
def extract_case(body: DocumentRequest, request: Request) -> dict:
    document = body.model_dump()
    try:
        raw = request.app.state.extractor(document)
        return validate_recognition(raw, document)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="文件辨識失敗，請稍後重試，或確認後端模型連線。") from exc
