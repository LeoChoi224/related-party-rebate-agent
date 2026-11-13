"""마스터 정정 신고.

MasterChange: 대리점 식별정보 정정 1건. 신고 원문, 이전 값, 새 값, 신고를 확인해 적용한 사람을 남긴다.
정정은 적용과 함께 관련자 그룹을 새 버전으로 다시 계산한다. 정정 전 · 후 버전을 모두 가리켜,
"이 정정 때문에 그룹이 어떻게 바뀌었나(또는 안 바뀌었나)"를 나중에도 설명할 수 있다.
값 자체는 IdentityAttribute 의 유효기간(valid_to · 새 행)으로 남고, 원본 대리점 마스터는 고치지 않는다.
MasterChangeReport: 정정 신고 문장 [주장] 과 그 AI 해석 [주장](19), 영업지원팀 확인 결과.
    적용하면 MasterChange 한 건이 생기고 change_id 로 가리킨다. 기각하면 정정은 없다.
    AI 해석이 없으면(대체 모드) 사람이 폼에 직접 넣은 값으로 적용하고 agreed 는 비어 있다.
"""

from datetime import date, datetime

from sqlalchemy import JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MasterChange(Base):
    __tablename__ = "master_change"

    change_id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agency.agency_id"))
    attr_type: Mapped[str]
    old_value: Mapped[str]
    new_value: Mapped[str]
    # 이 날짜부터 새 값이 유효하다(이전 값의 valid_to, 새 값의 valid_from).
    effective_date: Mapped[date]
    # 대리점이 신고한 문장 그대로. 입력 폼으로 넣으면 비어 있을 수 있다.
    reported_text: Mapped[str | None]
    reported_by: Mapped[str]
    # 대리점이 신고한 값이라 [주장] 이다. 원본 마스터와 다른 출처로 구분한다.
    provenance: Mapped[str]
    group_version_before: Mapped[int | None] = mapped_column(
        ForeignKey("group_version.group_version_id")
    )
    group_version_after: Mapped[int | None] = mapped_column(
        ForeignKey("group_version.group_version_id")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MasterChangeReport(Base):
    __tablename__ = "master_change_report"

    report_id: Mapped[int] = mapped_column(primary_key=True)
    raw_text: Mapped[str]
    provenance: Mapped[str]
    reported_by: Mapped[str]
    status: Mapped[str]
    # AI 해석 [주장]. 해석 전이거나 대체 모드면 비어 있다.
    ai_agency_id: Mapped[str | None]
    ai_attr_type: Mapped[str | None]
    ai_new_value: Mapped[str | None]
    ai_effective_date: Mapped[date | None]
    ai_confidence: Mapped[float | None]
    # 가드가 찾은 문제(대체 모드가 된 이유 포함). 통과하면 빈 목록.
    problems: Mapped[list[str]] = mapped_column(JSON, default=list)
    verified: Mapped[bool] = mapped_column(default=False)
    fallback_used: Mapped[bool] = mapped_column(default=False)
    model: Mapped[str | None]
    # 영업지원팀 확인. 적용이면 정정 건을 가리키고, AI 해석과 같은 값으로 적용했는지 남긴다.
    change_id: Mapped[int | None] = mapped_column(ForeignKey("master_change.change_id"))
    decision_reason: Mapped[str | None]
    decided_by: Mapped[str | None]
    decided_at: Mapped[datetime | None]
    agreed: Mapped[bool | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
