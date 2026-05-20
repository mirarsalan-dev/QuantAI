import logging
import os
import firebase_admin
from firebase_admin import credentials, firestore

# Constants (avoid magic numbers)
LOOKBACK_DAYS = 729
TRAIN_TEST_SPLIT = 0.85
RSI_THRESHOLD = 40

FIREBASE_KEY_FILE = 'firebase_key.json'

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('quantai')

# Initialize Firebase safely — do not surface errors to UI
db = None
try:
    if not firebase_admin._apps:
        if os.path.exists(FIREBASE_KEY_FILE):
            cred = credentials.Certificate(FIREBASE_KEY_FILE)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
        else:
            logger.warning("Firebase key file not found: %s", FIREBASE_KEY_FILE)
            # DB remains None; do not attempt to call firestore.client()
    else:
        db = firestore.client()
except Exception as e:
    logger.exception("Firebase initialization failed — continuing without DB: %s", e)

# Expose availability flag for other modules
FIREBASE_AVAILABLE = db is not None
