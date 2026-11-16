from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Row:
    id: Mapped[int] = mapped_column(primary_key=True)


class Timestamp:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)


class Preferences(Base):
    __tablename__ = "settings"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    keywords: Mapped[str] = mapped_column(default="")
    min_rub: Mapped[int] = mapped_column(default=0)
    max_level: Mapped[int] = mapped_column(default=3)
    notify: Mapped[bool] = mapped_column(default=True)


class Source(Row, Base):
    __tablename__ = "sources"
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    kind: Mapped[str] = mapped_column(String(8))
    enabled: Mapped[bool] = mapped_column(default=True)
    last_result: Mapped[str] = mapped_column(default="ещё не проверен")


class Job(Row, Timestamp, Base):
    __tablename__ = "jobs"
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    brief: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None]
    budget_rub: Mapped[int | None]
    level: Mapped[int | None]


class Analysis(Row, Timestamp, Base):
    __tablename__ = "analyses"
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    body: Mapped[str] = mapped_column(Text)


class Draft(Row, Timestamp, Base):
    __tablename__ = "drafts"
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    body: Mapped[str] = mapped_column(Text)


class Project(Row, Timestamp, Base):
    __tablename__ = "projects"
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))


class Artifact(Row, Base):
    __tablename__ = "artifacts"
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True)
    payload: Mapped[bytes]


class Notification(Row, Base):
    __tablename__ = "notifications"
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    sent: Mapped[bool] = mapped_column(default=False, index=True)


class Usage(Row, Base):
    __tablename__ = "ai_usage"
    day: Mapped[date] = mapped_column(index=True)
    model: Mapped[str]
    task: Mapped[str]
    tokens: Mapped[int]
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 9))
    state: Mapped[str] = mapped_column(default="reserved")
