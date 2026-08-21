import hashlib, json, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AuditAnchor, AuditEvent, Encounter, LegalHold, RetentionSnapshot, User
from app.services.audit_ledger_service import ZERO_HASH, encounter_forensic_export, verify_chain
from app.services.security_service import audit


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True).encode()




def _encryption_key() -> bytes:
    raw=(settings.retention_encryption_key_hex or "").strip()
    try: key=bytes.fromhex(raw)
    except ValueError as exc: raise ValueError("RETENTION_ENCRYPTION_KEY_HEX must be valid hex") from exc
    if len(key)!=32: raise ValueError("RETENTION_ENCRYPTION_KEY_HEX must contain exactly 32 bytes (64 hex characters)")
    return key

def _encrypt_payload(payload: bytes) -> bytes:
    nonce=os.urandom(12)
    ciphertext=AESGCM(_encryption_key()).encrypt(nonce,payload,b"medinote-retention-v0.1")
    return _canonical({"format":"medinote-encrypted-retention-v0.1","algorithm":"AES-256-GCM","nonce_hex":nonce.hex(),"ciphertext_hex":ciphertext.hex()})

def _decrypt_payload(envelope: bytes) -> bytes:
    obj=json.loads(envelope)
    if obj.get("algorithm")!="AES-256-GCM": raise ValueError("Unsupported retention encryption algorithm")
    return AESGCM(_encryption_key()).decrypt(bytes.fromhex(obj["nonce_hex"]),bytes.fromhex(obj["ciphertext_hex"]),b"medinote-retention-v0.1")

def _store_dir(org_id: UUID) -> Path:
    path = Path(settings.immutable_store_path) / str(org_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_worm(path: Path, payload: bytes) -> str:
    # O_EXCL prevents replacement through this service. Production should use object-lock/WORM storage.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    return hashlib.sha256(payload).hexdigest()


def create_external_anchor(db: Session, user: User) -> dict:
    chain = verify_chain(db, user.organization_id)
    if not chain['valid']:
        raise ValueError('Audit chain invalid; external anchor refused')
    previous = db.scalar(select(AuditAnchor).where(AuditAnchor.organization_id==user.organization_id).order_by(AuditAnchor.sequence_number.desc()).limit(1))
    seq = (previous.sequence_number + 1) if previous else 1
    payload = {
        'format': 'medinote-audit-anchor-v0.1',
        'organization_id': str(user.organization_id),
        'anchor_sequence': seq,
        'audit_event_count': chain['events'],
        'audit_head_hash': chain['head_hash'],
        'previous_anchor_sha256': previous.artifact_sha256 if previous else ZERO_HASH,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    raw=_canonical(payload)
    path=_store_dir(user.organization_id)/f'anchor-{seq:08d}.json'
    digest=_write_worm(path,raw)
    row=AuditAnchor(organization_id=user.organization_id,sequence_number=seq,audit_event_count=chain['events'],audit_head_hash=chain['head_hash'],artifact_sha256=digest,storage_uri=str(path),created_by=user.id)
    db.add(row)
    audit(db,user=user,event_type='audit_anchor_created',object_type='audit_anchor',object_id=row.id,metadata={'sequence_number':seq,'audit_event_count':chain['events'],'audit_head_hash':chain['head_hash'],'artifact_sha256':digest})
    db.commit(); db.refresh(row)
    return {'anchor_id':str(row.id),**payload,'artifact_sha256':digest,'storage_uri':str(path)}


def verify_external_anchors(db: Session, organization_id: UUID) -> dict:
    anchors=list(db.scalars(select(AuditAnchor).where(AuditAnchor.organization_id==organization_id).order_by(AuditAnchor.sequence_number)))
    issues=[]; prev=ZERO_HASH
    for idx,a in enumerate(anchors,1):
        if a.sequence_number!=idx: issues.append({'anchor_id':str(a.id),'issue':'sequence_gap'})
        path=Path(a.storage_uri)
        if not path.exists(): issues.append({'anchor_id':str(a.id),'issue':'artifact_missing'}); continue
        raw=path.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
        if digest!=a.artifact_sha256: issues.append({'anchor_id':str(a.id),'issue':'artifact_hash_mismatch'})
        try: payload=json.loads(raw)
        except Exception: issues.append({'anchor_id':str(a.id),'issue':'artifact_invalid_json'}); continue
        if payload.get('audit_head_hash')!=a.audit_head_hash: issues.append({'anchor_id':str(a.id),'issue':'head_hash_mismatch'})
        if payload.get('previous_anchor_sha256')!=prev: issues.append({'anchor_id':str(a.id),'issue':'anchor_chain_mismatch'})
        prev=a.artifact_sha256
    return {'organization_id':str(organization_id),'anchors':len(anchors),'valid':not issues,'head_anchor_sha256':prev,'issues':issues}


def active_legal_holds(db: Session, organization_id: UUID, encounter_id: UUID | None=None):
    q=select(LegalHold).where(LegalHold.organization_id==organization_id,LegalHold.status=='active')
    holds=list(db.scalars(q))
    if encounter_id is None: return holds
    return [h for h in holds if h.encounter_id is None or h.encounter_id==encounter_id]


def place_legal_hold(db: Session,user:User,matter_reference:str,reason:str,encounter_id:UUID|None=None):
    if encounter_id:
        enc=db.get(Encounter,encounter_id)
        if not enc or enc.organization_id!=user.organization_id: raise LookupError('Encounter not found')
    row=LegalHold(organization_id=user.organization_id,encounter_id=encounter_id,matter_reference=matter_reference,reason=reason,placed_by=user.id)
    db.add(row); db.flush()
    audit(db,user=user,event_type='legal_hold_placed',encounter_id=encounter_id,object_type='legal_hold',object_id=row.id,metadata={'matter_reference':matter_reference,'scope':'encounter' if encounter_id else 'organization'})
    db.commit(); db.refresh(row); return row


def release_legal_hold(db: Session,user:User,hold_id:UUID,reason:str):
    row=db.get(LegalHold,hold_id)
    if not row or row.organization_id!=user.organization_id: raise LookupError('Legal hold not found')
    if row.status!='active': raise ValueError('Legal hold is not active')
    row.status='released'; row.released_by=user.id; row.released_at=datetime.now(timezone.utc); row.release_reason=reason
    audit(db,user=user,event_type='legal_hold_released',encounter_id=row.encounter_id,object_type='legal_hold',object_id=row.id,metadata={'matter_reference':row.matter_reference})
    db.commit(); db.refresh(row); return row


def create_retention_snapshot(db:Session,user:User,encounter_id:UUID,retention_days:int|None=None):
    export=encounter_forensic_export(db,user.organization_id,encounter_id,include_content=False)
    holds=active_legal_holds(db,user.organization_id,encounter_id)
    days=retention_days if retention_days is not None else settings.default_retention_days
    retention_until=None if holds else datetime.now(timezone.utc)+timedelta(days=days)
    payload={'format':'medinote-retention-v0.1','encounter_id':str(encounter_id),'organization_id':str(user.organization_id),'retention_until':retention_until.isoformat() if retention_until else None,'legal_hold_active':bool(holds),'forensic_export':export}
    plaintext=_canonical(payload)
    encrypted=_encrypt_payload(plaintext)
    digest=hashlib.sha256(encrypted).hexdigest()
    path=_store_dir(user.organization_id)/f'encounter-{encounter_id}-{digest[:16]}.enc.json'
    _write_worm(path,encrypted)
    row=RetentionSnapshot(organization_id=user.organization_id,encounter_id=encounter_id,content_sha256=digest,storage_uri=str(path),retention_until=retention_until,legal_hold_active=bool(holds),created_by=user.id)
    db.add(row); db.flush()
    audit(db,user=user,event_type='retention_snapshot_created',encounter_id=encounter_id,object_type='retention_snapshot',object_id=row.id,metadata={'content_sha256':digest,'legal_hold_active':bool(holds),'retention_until':retention_until.isoformat() if retention_until else None})
    db.commit(); db.refresh(row)
    return row


def retention_status(db:Session,organization_id:UUID,encounter_id:UUID):
    enc=db.get(Encounter,encounter_id)
    if not enc or enc.organization_id!=organization_id: raise LookupError('Encounter not found')
    holds=active_legal_holds(db,organization_id,encounter_id)
    snaps=list(db.scalars(select(RetentionSnapshot).where(RetentionSnapshot.organization_id==organization_id,RetentionSnapshot.encounter_id==encounter_id).order_by(RetentionSnapshot.created_at.desc())))
    now=datetime.now(timezone.utc)
    eligible=bool(snaps) and not holds and snaps[0].retention_until is not None and snaps[0].retention_until<=now
    return {'encounter_id':str(encounter_id),'legal_hold_active':bool(holds),'active_holds':[{'hold_id':str(h.id),'matter_reference':h.matter_reference,'scope':'encounter' if h.encounter_id else 'organization'} for h in holds],'latest_snapshot':({'snapshot_id':str(snaps[0].id),'content_sha256':snaps[0].content_sha256,'retention_until':snaps[0].retention_until,'storage_uri':snaps[0].storage_uri} if snaps else None),'eligible_for_deletion':eligible}


def verify_retention_snapshot(db:Session,organization_id:UUID,snapshot_id:UUID,decrypt:bool=False):
    row=db.get(RetentionSnapshot,snapshot_id)
    if not row or row.organization_id!=organization_id: raise LookupError("Retention snapshot not found")
    path=Path(row.storage_uri)
    if not path.exists(): return {"snapshot_id":str(row.id),"valid":False,"issue":"artifact_missing"}
    raw=path.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
    result={"snapshot_id":str(row.id),"valid":digest==row.content_sha256,"artifact_sha256":digest,"expected_sha256":row.content_sha256,"encrypted":True}
    if decrypt and result["valid"]:
        plaintext=_decrypt_payload(raw); payload=json.loads(plaintext); result["payload_sha256"]=hashlib.sha256(plaintext).hexdigest(); result["payload"]=payload
    return result
