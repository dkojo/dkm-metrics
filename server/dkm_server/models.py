"""The four core tables: Project, Experiment, Variant, Event."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    """One LLM application. Authenticates with its API key."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    api_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    experiments: Mapped[list["Experiment"]] = relationship(back_populates="project")


class Experiment(Base):
    """Something being tested, e.g. 'support-bot system prompt'."""

    __tablename__ = "experiments"
    __table_args__ = (UniqueConstraint("project_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | running | stopped
    primary_metric: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="experiments")
    variants: Mapped[list["Variant"]] = relationship(
        back_populates="experiment", order_by="Variant.position", cascade="all, delete-orphan"
    )


class Variant(Base):
    """One option in an experiment. `config` is arbitrary JSON (prompt, model, params...).
    The first variant (position 0) is the control."""

    __tablename__ = "variants"
    __table_args__ = (UniqueConstraint("experiment_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    key: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(default=0)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    experiment: Mapped[Experiment] = relationship(back_populates="variants")


class Event(Base):
    """One metric observation: (experiment, variant, user, metric, value)."""

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_exp_metric", "experiment_id", "metric"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id"))
    user_id: Mapped[str] = mapped_column(String(200))
    metric: Mapped[str] = mapped_column(String(100))
    value: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
