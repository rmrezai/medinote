import json
from pathlib import Path
from sqlalchemy import select
from app.models import ValidationCase

def seed_validation_cases(db):
    path = Path(__file__).resolve().parents[2] / 'validation' / 'cases' / 'core_cases.json'
    if not path.exists(): return 0
    data = json.loads(path.read_text())
    count=0
    for item in data:
        existing = db.scalar(select(ValidationCase).where(ValidationCase.slug == item['slug']))
        if existing:
            # Keep seed content/version current for reproducible local development.
            existing.title=item['title']; existing.category=item['category']; existing.source_text=item['source_text']
            existing.ground_truth=item['ground_truth']; existing.module_targets=item.get('module_targets',[])
            existing.hazard_tags=item.get('hazard_tags',[]); existing.difficulty=item.get('difficulty','standard'); existing.version=item.get('version','1.0')
            continue
        db.add(ValidationCase(**item)); count += 1
    db.commit()
    return count
