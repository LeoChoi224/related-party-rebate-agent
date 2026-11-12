"""관련자 그룹(버전 단위).

GroupVersion: 그룹 계산 1회분. 버전 1 은 앱을 켤 때 시더가 만들고,
정정 신고로 다시 계산하면 새 버전이 생긴다. 무엇 때문에 다시 계산했는지
(trigger_change_id)는 MASTER_CHANGE 표가 생기는 20 에서 더한다.
RelatedGroup, GroupMember: 버전별 그룹과 구성원. 2곳 이상 묶인 그룹만 저장한다.
RelationEdge: 1개 이상 일치한 두 대리점. 일치 속성마다 값과 양쪽 근거 행, 판정(관련자·정황)을 담는다.
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GroupVersion(Base):
    __tablename__ = "group_version"

    group_version_id: Mapped[int] = mapped_column(primary_key=True)
    version_no: Mapped[int]
    is_current: Mapped[bool]
    # SQLite CURRENT_TIMESTAMP 라 UTC 로 저장된다. 화면에 보여 줄 때 바꾼다.
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RelatedGroup(Base):
    __tablename__ = "related_group"

    group_id: Mapped[int] = mapped_column(primary_key=True)
    group_version_id: Mapped[int] = mapped_column(
        ForeignKey("group_version.group_version_id")
    )
    label: Mapped[str]


class GroupMember(Base):
    __tablename__ = "group_member"

    # 두 컬럼을 합친 기본키라 한 그룹에 같은 대리점이 두 번 들어가지 않는다.
    group_id: Mapped[int] = mapped_column(
        ForeignKey("related_group.group_id"), primary_key=True
    )
    agency_id: Mapped[str] = mapped_column(
        ForeignKey("agency.agency_id"), primary_key=True
    )


class RelationEdge(Base):
    __tablename__ = "relation_edge"

    edge_id: Mapped[int] = mapped_column(primary_key=True)
    group_version_id: Mapped[int] = mapped_column(
        ForeignKey("group_version.group_version_id")
    )
    # agency_a 가 작은 ID 다.
    agency_a: Mapped[str] = mapped_column(ForeignKey("agency.agency_id"))
    agency_b: Mapped[str] = mapped_column(ForeignKey("agency.agency_id"))
    # list[dict] 는 SQLAlchemy 가 컬럼 타입을 스스로 정하지 못해 JSON 을 직접 적는다.
    matched_attrs: Mapped[list[dict]] = mapped_column(JSON)
    match_count: Mapped[int]
    judgement: Mapped[str]
