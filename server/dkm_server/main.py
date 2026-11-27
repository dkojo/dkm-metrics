"""dkm-metrics API server."""

import logging
import os
import secrets
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import stats
from .db import Base, SessionLocal, engine, get_db
from .models import Event, Experiment, Project, Variant
from .schemas import (
    EventBatch,
    ExperimentIn,
    ExperimentOut,
    ExperimentUpdate,
    IngestResult,
    VariantOut,
)

log = logging.getLogger("dkm")


def ensure_default_project() -> None:
    """Create the default project on first start. Its key comes from DKM_API_KEY or is generated."""
    with SessionLocal() as db:
        if db.scalar(select(Project).limit(1)):
            return
        key = os.getenv("DKM_API_KEY") or f"dkm_{secrets.token_urlsafe(24)}"
        db.add(Project(name="default", api_key=key))
        db.commit()
        print(f"\n  dkm-metrics API key: {key}\n", flush=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    ensure_default_project()
    yield


app = FastAPI(title="dkm-metrics", version="0.1.0", lifespan=lifespan)


# ---------- auth ----------

def current_project(
    authorization: str = Header(default=""), db: Session = Depends(get_db)
) -> Project:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Missing 'Authorization: Bearer <api key>' header")
    project = db.scalar(select(Project).where(Project.api_key == token))
    if not project:
        raise HTTPException(401, "Invalid API key")
    return project


# ---------- helpers ----------

def get_experiment(db: Session, project: Project, key: str) -> Experiment:
    exp = db.scalar(
        select(Experiment).where(Experiment.project_id == project.id, Experiment.key == key)
    )
    if not exp:
        raise HTTPException(404, f"Experiment '{key}' not found")
    return exp


def event_count(db: Session, exp: Experiment) -> int:
    return db.scalar(select(func.count()).where(Event.experiment_id == exp.id)) or 0


def to_out(exp: Experiment, count: int = 0) -> ExperimentOut:
    return ExperimentOut(
        key=exp.key,
        name=exp.name,
        description=exp.description,
        status=exp.status,
        primary_metric=exp.primary_metric,
        created_at=exp.created_at,
        variants=[VariantOut(key=v.key, weight=v.weight, config=v.config) for v in exp.variants],
        event_count=count,
    )


# ---------- dashboard / management routes ----------

@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/experiments", response_model=list[ExperimentOut])
def list_experiments(project: Project = Depends(current_project), db: Session = Depends(get_db)):
    exps = db.scalars(
        select(Experiment)
        .where(Experiment.project_id == project.id)
        .order_by(Experiment.created_at.desc(), Experiment.id.desc())
    ).all()
    counts = dict(
        db.execute(
            select(Event.experiment_id, func.count())
            .where(Event.experiment_id.in_([e.id for e in exps]))
            .group_by(Event.experiment_id)
        ).all()
    )
    return [to_out(e, counts.get(e.id, 0)) for e in exps]


@app.post("/api/experiments", response_model=ExperimentOut, status_code=201)
def create_experiment(
    body: ExperimentIn, project: Project = Depends(current_project), db: Session = Depends(get_db)
):
    exp = Experiment(
        project_id=project.id,
        key=body.key,
        name=body.name,
        description=body.description,
        primary_metric=body.primary_metric,
        variants=[
            Variant(key=v.key, position=i, weight=v.weight, config=v.config)
            for i, v in enumerate(body.variants)
        ],
    )
    db.add(exp)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Experiment '{body.key}' already exists")
    return to_out(exp)


@app.get("/api/experiments/{key}", response_model=ExperimentOut)
def read_experiment(key: str, project: Project = Depends(current_project), db: Session = Depends(get_db)):
    exp = get_experiment(db, project, key)
    return to_out(exp, event_count(db, exp))


@app.patch("/api/experiments/{key}", response_model=ExperimentOut)
def update_experiment(
    key: str,
    body: ExperimentUpdate,
    project: Project = Depends(current_project),
    db: Session = Depends(get_db),
):
    exp = get_experiment(db, project, key)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(exp, field, value)
    db.commit()
    return to_out(exp, event_count(db, exp))


@app.delete("/api/experiments/{key}", status_code=204)
def delete_experiment(key: str, project: Project = Depends(current_project), db: Session = Depends(get_db)):
    exp = get_experiment(db, project, key)
    db.execute(delete(Event).where(Event.experiment_id == exp.id))
    db.delete(exp)
    db.commit()
    return Response(status_code=204)


@app.get("/api/experiments/{key}/results")
def experiment_results(key: str, project: Project = Depends(current_project), db: Session = Depends(get_db)):
    exp = get_experiment(db, project, key)
    variant_keys = {v.id: v.key for v in exp.variants}
    control = exp.variants[0].key

    rows = db.execute(
        select(Event.metric, Event.variant_id, Event.value, Event.user_id).where(
            Event.experiment_id == exp.id
        )
    ).all()

    values: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {k: [] for k in variant_keys.values()}
    )
    users: dict[str, set[str]] = {k: set() for k in variant_keys.values()}
    for metric, variant_id, value, user_id in rows:
        vk = variant_keys[variant_id]
        values[metric][vk].append(value)
        users[vk].add(user_id)

    # Primary metric first, then alphabetical.
    metrics = sorted(values, key=lambda m: (m != exp.primary_metric, m))
    return {
        "experiment": exp.key,
        "status": exp.status,
        "control": control,
        "primary_metric": exp.primary_metric,
        "users": {k: len(u) for k, u in users.items()},
        "metrics": [stats.analyze(m, values[m], control) for m in metrics],
    }


# ---------- SDK routes ----------

@app.get("/api/sdk/config")
def sdk_config(project: Project = Depends(current_project), db: Session = Depends(get_db)):
    """Everything the SDK needs to assign variants locally: all running experiments."""
    exps = db.scalars(
        select(Experiment).where(Experiment.project_id == project.id, Experiment.status == "running")
    ).all()
    return {
        "experiments": {
            e.key: {
                "variants": [
                    {"key": v.key, "weight": v.weight, "config": v.config} for v in e.variants
                ]
            }
            for e in exps
        }
    }


@app.post("/api/events", response_model=IngestResult)
def ingest_events(
    body: EventBatch, project: Project = Depends(current_project), db: Session = Depends(get_db)
):
    """Batch ingest. Events for unknown or non-running experiments/variants are rejected."""
    exps = db.scalars(
        select(Experiment).where(
            Experiment.project_id == project.id,
            Experiment.key.in_({e.experiment for e in body.events}),
            Experiment.status == "running",
        )
    ).all()
    lookup = {(e.key, v.key): (e.id, v.id) for e in exps for v in e.variants}

    accepted = 0
    for ev in body.events:
        ids = lookup.get((ev.experiment, ev.variant))
        if not ids:
            continue
        row = Event(
            experiment_id=ids[0],
            variant_id=ids[1],
            user_id=ev.user_id,
            metric=ev.metric,
            value=ev.value,
        )
        if ev.timestamp:
            row.created_at = ev.timestamp
        db.add(row)
        accepted += 1
    db.commit()
    return IngestResult(accepted=accepted, rejected=len(body.events) - accepted)
