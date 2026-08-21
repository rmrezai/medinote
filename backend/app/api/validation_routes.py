from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import User, ValidationCase, ValidationRun
from app.schemas.validation import (
    ValidationAdjudicateRequest, ValidationCaseRead, ValidationDashboard,
    ValidationEvaluateRequest, ValidationReport, ValidationRunRead,
)
from app.services.security_service import current_user
from app.services.validation_service import build_dashboard, build_report, evaluate, MODULES

router = APIRouter(prefix='/api/v1/validation', tags=['validation'])

@router.get('/cases', response_model=list[ValidationCaseRead])
def cases(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(ValidationCase).order_by(ValidationCase.category, ValidationCase.slug)))

@router.get('/cases/{case_id}', response_model=ValidationCaseRead)
def case(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    obj = db.get(ValidationCase, case_id)
    if not obj: raise HTTPException(404, 'Validation case not found')
    return obj

@router.post('/cases/{case_id}/evaluate', response_model=ValidationRunRead)
def evaluate_case(case_id: UUID, payload: ValidationEvaluateRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = db.get(ValidationCase, case_id)
    if not case: raise HTTPException(404, 'Validation case not found')
    if payload.module not in MODULES: raise HTTPException(422, 'Unsupported validation module')
    m = evaluate(case.ground_truth, payload.observed, payload.generated_text, payload.physician_final_text)
    run = ValidationRun(
        validation_case_id=case.id, organization_id=user.organization_id, reviewer_id=user.id,
        module=payload.module, scenario_injections=payload.scenario_injections,
        observed=payload.observed, metrics=m, physician_edit_ratio=m.get('physician_edit_ratio'),
        consequential_error_count=m['consequential_errors'], reviewer_scores=payload.reviewer_scores,
        passed=bool(m['passed'])
    )
    db.add(run); db.commit(); db.refresh(run); return run

@router.post('/runs/{run_id}/adjudicate', response_model=ValidationRunRead)
def adjudicate(run_id: UUID, payload: ValidationAdjudicateRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.get(ValidationRun, run_id)
    if not run or run.organization_id != user.organization_id: raise HTTPException(404, 'Validation run not found')
    if payload.status not in {'accepted','rejected','resolved'}: raise HTTPException(422, 'Unsupported adjudication status')
    run.adjudication_status = payload.status
    run.adjudication_notes = payload.notes
    if payload.reviewer_scores: run.reviewer_scores = payload.reviewer_scores
    db.commit(); db.refresh(run); return run

@router.get('/dashboard', response_model=ValidationDashboard)
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cs = list(db.scalars(select(ValidationCase)))
    rs = list(db.scalars(select(ValidationRun).where(ValidationRun.organization_id == user.organization_id)))
    return ValidationDashboard(**build_dashboard(cs, rs))

@router.get('/report', response_model=ValidationReport)
def report(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cs = list(db.scalars(select(ValidationCase)))
    rs = list(db.scalars(select(ValidationRun).where(ValidationRun.organization_id == user.organization_id)))
    dash = build_dashboard(cs, rs)
    return ValidationReport(**build_report(cs, rs, dash))
