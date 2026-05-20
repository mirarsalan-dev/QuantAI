import re
import logging
from typing import Optional
import bcrypt
from firebase_admin import firestore
from config import db, logger


USERNAME_RE = re.compile(r'^[A-Za-z0-9_\-]{3,32}$')


def validate_username(username: str) -> bool:
    return bool(username and USERNAME_RE.match(username))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        logger.exception("Password check failed")
        return False


def create_user(username: str, password: str) -> bool:
    if not validate_username(username):
        return False
    if not password or len(password) < 4:
        return False
    if db is None:
        logger.error("Attempted to create user but Firebase DB is not available")
        return False

    doc_ref = db.collection('users').document(username)
    try:
        snap = doc_ref.get()
        if snap.exists:
            return False
        doc_ref.set({'password': hash_password(password), 'created_at': firestore.SERVER_TIMESTAMP})
        return True
    except Exception:
        logger.exception("Failed to create user %s", username)
        return False


def login_user(username: str, password: str) -> bool:
    if not validate_username(username):
        return False
    if db is None:
        logger.error("Attempted login but Firebase DB is not available")
        return False

    try:
        doc_ref = db.collection('users').document(username)
        doc = doc_ref.get()
        if not doc.exists:
            return False
        stored = doc.to_dict().get('password')
        if not stored:
            return False
        return check_password(password, stored)
    except Exception:
        logger.exception("Login failed for %s", username)
        return False
