"""모든 ORM 모델이 상속하는 Declarative Base."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
