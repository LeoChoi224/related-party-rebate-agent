"""마스터 정정 신고 스키마.

MasterChangeRequest: 정정 신고 요청. 정정할 수 있는 속성은 대표자 · 주소 · 등록계좌다.
    실입금계좌는 돈이 실제로 들어온 사실이라 신고로 고칠 수 없다.
MasterChangeResult: 적용 결과. 그룹이 어떻게 바뀌었는지(또는 유지되었는지), 근거 쌍, 다시 판정한 건.
MasterChangeParse · ReportCreate · ReportDecision · ReportOut · ReportDecisionResult: 신고 문장 AI 해석(19).
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import IdentityAttrType
from app.schemas.common import UtcDatetime
from app.schemas.related_party import RelationEdgeOut

CORRECTABLE = (
    IdentityAttrType.REPRESENTATIVE,
    IdentityAttrType.ADDRESS,
    IdentityAttrType.REGISTERED_ACCOUNT,
)


class MasterChangeRequest(BaseModel):
    attr_type: IdentityAttrType
    new_value: str = Field(min_length=1, examples=["대전시 중앙로 260"])
    # 비우면 서버의 오늘 날짜.
    effective_date: date | None = None
    reported_text: str = ""
    actor: str = Field(min_length=1, examples=["김지원"])
    role: str = Field(min_length=1, examples=["영업지원팀"])

    @model_validator(mode="after")
    def correctable_and_not_blank(self) -> "MasterChangeRequest":
        if self.attr_type not in CORRECTABLE:
            raise ValueError("대표자 · 주소 · 등록계좌만 정정할 수 있습니다")
        if not self.new_value.strip():
            raise ValueError("새 값을 입력해야 합니다")
        return self


class RejudgeRequest(BaseModel):
    actor: str = Field(min_length=1, examples=["김지원"])
    role: str = Field(min_length=1, examples=["영업지원팀"])


class MasterChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    change_id: int
    agency_id: str
    attr_type: str
    old_value: str
    new_value: str
    effective_date: date
    reported_text: str | None
    reported_by: str
    provenance: str
    created_at: UtcDatetime


class GroupOut(BaseModel):
    label: str
    members: list[str]


class ClaimImpactOut(BaseModel):
    """정정으로 판정 단위가 바뀐 건 하나. 재판정 전(재검토필요로 남음)이면 *_after 가 비어 있다."""

    rebate_id: str
    agency_id: str
    period_ym: str
    from_status: str
    to_status: str
    min_authority_before: str | None
    min_authority_after: str | None
    group_sum_before: int | None
    group_sum_after: int | None
    approval_request_id: int | None


class MasterChangeResult(BaseModel):
    change: MasterChangeOut
    version_no_before: int
    version_no_after: int
    groups_before: list[GroupOut]
    groups_after: list[GroupOut]
    # 같은 구성원으로 묶인 그룹이 그대로면 참(결론 유지). 라벨이 바뀌어도 구성원이 같으면 유지다.
    group_retained: bool
    # 정정 때문에 소속 그룹이 달라진 대리점
    affected_agencies: list[str]
    # 정정한 대리점이 낀 새 버전의 일치 쌍. 유지 · 변경 어느 쪽이든 왜 그런지 근거 행으로 보여 준다.
    evidence: list[RelationEdgeOut]
    claims: list[ClaimImpactOut]


class RejudgeResult(BaseModel):
    rebate_id: str
    status: str
    min_authority: str | None
    group_sum_krw: int | None
    approval_request_id: int | None


# 정정할 수 있는 속성 이름. LLM 구조화 출력이 이 셋 밖의 값을 내지 못하게 Literal 로 둔다.
CorrectableAttr = Literal["대표자", "주소", "등록계좌"]


class MasterChangeParse(BaseModel):
    """정정 신고 문장의 AI 해석(19). 필드 설명이 그대로 LLM 지시가 된다."""

    # 범위 제약은 넣지 않는다(ClaimAssessment 와 같은 이유). 값의 검사는 가드가 한다.
    agency_id: str = Field(
        description="정정 대상 대리점 ID(D-000 형식). 문장에 이름만 있으면 대리점 목록에서 찾은 ID"
    )
    attr_type: CorrectableAttr = Field(
        description="정정할 속성: 대표자 · 주소 · 등록계좌"
    )
    new_value: str = Field(
        description="새 값. 문장에 적힌 글자를 그대로 옮기고 고쳐 쓰지 않는다"
    )
    effective_date: date | None = Field(
        description="정정일(YYYY-MM-DD). 문장에 날짜가 없으면 null"
    )
    confidence: float = Field(description="해석에 대한 확신도. 0 에서 1 사이")


class ReportCreate(BaseModel):
    raw_text: str = Field(
        min_length=1,
        examples=["D-041 대리점입니다. 본사를 대전시 중앙로 260 으로 이전했습니다."],
    )
    actor: str = Field(min_length=1, examples=["김지원"])
    role: str = Field(min_length=1, examples=["영업지원팀"])

    @model_validator(mode="after")
    def not_blank(self) -> "ReportCreate":
        if not self.raw_text.strip():
            raise ValueError("신고 문장을 입력해야 합니다")
        return self


class ReportDecision(BaseModel):
    """영업지원팀 확인. 적용이면 사람이 확인(또는 고친) 값으로 정정한다. 기각은 사유가 필요하다."""

    apply: bool
    agency_id: str = ""
    attr_type: CorrectableAttr | None = None
    new_value: str = ""
    effective_date: date | None = None
    reason: str = ""
    actor: str = Field(min_length=1, examples=["김지원"])
    role: str = Field(min_length=1, examples=["영업지원팀"])

    @model_validator(mode="after")
    def fields_for_apply(self) -> "ReportDecision":
        if self.apply:
            if (
                not self.agency_id.strip()
                or self.attr_type is None
                or not self.new_value.strip()
            ):
                raise ValueError(
                    "적용하려면 대리점 · 속성 · 새 값을 모두 입력해야 합니다"
                )
        elif not self.reason.strip():
            raise ValueError("기각 사유를 입력해야 합니다")
        return self


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: int
    raw_text: str
    provenance: str
    reported_by: str
    status: str
    ai_agency_id: str | None
    ai_attr_type: str | None
    ai_new_value: str | None
    ai_effective_date: date | None
    ai_confidence: float | None
    problems: list[str]
    verified: bool
    fallback_used: bool
    model: str | None
    change_id: int | None
    decision_reason: str | None
    decided_by: str | None
    decided_at: UtcDatetime | None
    agreed: bool | None
    created_at: UtcDatetime


class ReportDecisionResult(BaseModel):
    """확인 결과. 적용이면 정정 적용 결과(그룹 변화 · 다시 판정된 건)가 함께 온다."""

    report: ReportOut
    result: MasterChangeResult | None
