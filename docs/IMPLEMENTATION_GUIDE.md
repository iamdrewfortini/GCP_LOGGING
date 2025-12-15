# Glass Pane Enhancement Implementation Guide

**Quick Start**: Step-by-step guide to implementing the enhancements outlined in ENHANCEMENT_ANALYSIS.md

## Prerequisites

- GCP Project: `diatonic-ai-gcp`
- Firebase project linked to GCP project
- Permissions: Firestore Admin, Cloud Functions Admin
- Firebase CLI installed: `npm install -g firebase-tools`

## Phase 1: Setup Firebase (30 minutes)

### Step 1: Initialize Firebase in GCP Console

```bash
# 1. Go to Firebase Console: https://console.firebase.google.com
# 2. Add Firebase to existing GCP project (diatonic-ai-gcp)
# 3. Enable Firestore in Native mode (us-central1)
# 4. Enable Authentication with Email/Password provider
```

### Step 2: Deploy Firestore Configuration

```bash
# Login to Firebase
firebase login

# Initialize Firebase in this directory (already done - firebase.json exists)
# firebase init

# Deploy Firestore rules and indexes
firebase deploy --only firestore:rules
firebase deploy --only firestore:indexes

# Verify deployment
firebase firestore:indexes
```

### Step 3: Create Service Account for Backend

```bash
# Create service account for Cloud Run to access Firestore
gcloud iam service-accounts create glass-pane-firebase \
  --display-name="Glass Pane Firebase Service Account"

# Grant Firestore access
gcloud projects add-iam-policy-binding diatonic-ai-gcp \
  --member="serviceAccount:glass-pane-firebase@diatonic-ai-gcp.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# Grant AI Platform access (for embeddings)
gcloud projects add-iam-policy-binding diatonic-ai-gcp \
  --member="serviceAccount:glass-pane-firebase@diatonic-ai-gcp.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

## Phase 2: Update Backend (2 hours)

### Step 1: Install Firebase Admin SDK

```bash
# Add to requirements.txt
echo "firebase-admin>=6.4.0" >> requirements.txt
pip install -r requirements.txt
```

### Step 2: Initialize Firebase in Backend

Create `src/services/firebase_service.py`:

```python
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
import os

class FirebaseService:
    _instance = None
    _db = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._initialize_firebase()
        return cls._instance

    @classmethod
    def _initialize_firebase(cls):
        """Initialize Firebase Admin SDK"""
        if not firebase_admin._apps:
            # In Cloud Run, use Application Default Credentials
            # Locally, use GOOGLE_APPLICATION_CREDENTIALS env var
            firebase_admin.initialize_app()

        cls._db = firestore.client()

    @property
    def db(self):
        return self._db

    # Session Management
    def create_session(self, user_id: str, title: str = "New Session"):
        """Create a new AI chat session"""
        session_ref = self.db.collection('sessions').document()
        session_ref.set({
            'userId': user_id,
            'title': title,
            'status': 'active',
            'createdAt': firestore.SERVER_TIMESTAMP,
            'updatedAt': firestore.SERVER_TIMESTAMP,
            'metadata': {
                'totalMessages': 0,
                'totalCost': 0,
                'tags': []
            }
        })
        return session_ref.id

    def get_session(self, session_id: str):
        """Get session by ID"""
        return self.db.collection('sessions').document(session_id).get().to_dict()

    def list_sessions(self, user_id: str, status: str = 'active', limit: int = 50):
        """List user's sessions"""
        query = (self.db.collection('sessions')
                 .where(filter=FieldFilter('userId', '==', user_id))
                 .where(filter=FieldFilter('status', '==', status))
                 .order_by('updatedAt', direction=firestore.Query.DESCENDING)
                 .limit(limit))

        return [doc.to_dict() | {'id': doc.id} for doc in query.stream()]

    # Message Management
    def add_message(self, session_id: str, role: str, content: str, metadata: dict = None):
        """Add message to session"""
        message_ref = (self.db.collection('sessions')
                       .document(session_id)
                       .collection('messages')
                       .document())

        message_ref.set({
            'role': role,
            'content': content,
            'timestamp': firestore.SERVER_TIMESTAMP,
            'metadata': metadata or {}
        })

        # Update session metadata
        session_ref = self.db.collection('sessions').document(session_id)
        session_ref.update({
            'updatedAt': firestore.SERVER_TIMESTAMP,
            'metadata.totalMessages': firestore.Increment(1)
        })

        return message_ref.id

    def get_messages(self, session_id: str, limit: int = 100):
        """Get session messages"""
        query = (self.db.collection('sessions')
                 .document(session_id)
                 .collection('messages')
                 .order_by('timestamp')
                 .limit(limit))

        return [doc.to_dict() | {'id': doc.id} for doc in query.stream()]

# Singleton instance
firebase_service = FirebaseService()
```

### Step 3: Update Agent to Use Firebase

Modify `src/agent/agent.py` to persist state:

```python
from src.services.firebase_service import firebase_service

class LogDebuggerAgent:
    def __init__(self, session_id: str = None, user_id: str = "anonymous"):
        self.session_id = session_id or firebase_service.create_session(user_id)
        # ... rest of init

    async def stream_chat(self, message: str):
        # Save user message
        firebase_service.add_message(
            self.session_id,
            role='user',
            content=message
        )

        # Stream agent response
        full_response = ""
        async for chunk in self._generate_response(message):
            full_response += chunk
            yield chunk

        # Save assistant message
        firebase_service.add_message(
            self.session_id,
            role='assistant',
            content=full_response,
            metadata={'tokens': len(full_response.split())}
        )
```

## Phase 3: Update Frontend (3 hours)

### Step 1: Include Design System CSS

Update `src/glass_pane/templates/index.html`:

```html
<head>
    <!-- ... existing meta tags ... -->
    <link rel="stylesheet" href="/static/css/design-system.css">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Remove inline <style> tags and move to external files -->
</head>
```

### Step 2: Add Firebase SDK to Frontend

```html
<!-- Add before closing </body> tag -->
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-auth-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore-compat.js"></script>

<script>
// Initialize Firebase
const firebaseConfig = {
  apiKey: "{{ firebase_api_key }}",  // Pass from backend
  authDomain: "diatonic-ai-gcp.firebaseapp.com",
  projectId: "diatonic-ai-gcp",
  storageBucket: "diatonic-ai-gcp.appspot.com",
};

firebase.initializeApp(firebaseConfig);
const db = firebase.firestore();
const auth = firebase.auth();

// Real-time message subscription
function subscribeToSession(sessionId) {
  db.collection('sessions')
    .doc(sessionId)
    .collection('messages')
    .orderBy('timestamp')
    .onSnapshot(snapshot => {
      snapshot.docChanges().forEach(change => {
        if (change.type === 'added') {
          const message = change.doc.data();
          addChatMessage(message.content, message.role);
        }
      });
    });
}
</script>
```

## Phase 4: Deploy Enhanced AI Tools (4 hours)

### Step 1: Create Cloud Function for Embedding Generation

Create `functions/firebase/generate_embeddings/main.py`:

```python
import functions_framework
from google.cloud import firestore, aiplatform
from datetime import datetime, timedelta
import json

@functions_framework.cloud_event
def generate_log_embedding(cloud_event):
    """
    Triggered by Pub/Sub when ERROR/CRITICAL log arrives
    Generates embedding and stores in Firestore
    """
    db = firestore.Client()
    aiplatform.init(project="diatonic-ai-gcp", location="us-central1")

    # Parse log from Pub/Sub
    log_data = json.loads(cloud_event.data["message"]["data"])

    # Skip if not ERROR/CRITICAL
    if log_data.get('severity') not in ['ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY']:
        return

    # Generate embedding
    text = f"{log_data['severity']} | {log_data.get('service', 'unknown')} | {log_data.get('message', '')}"

    model = aiplatform.gapic.PredictionServiceClient()
    response = model.predict(
        endpoint="projects/diatonic-ai-gcp/locations/us-central1/publishers/google/models/text-embedding-004",
        instances=[{"content": text}]
    )

    embedding = response.predictions[0]["embeddings"]["values"]

    # Store in Firestore
    doc_ref = db.collection('embeddings').document()
    doc_ref.set({
        'vector': embedding,
        'text': text,
        'metadata': {
            'severity': log_data['severity'],
            'service': log_data.get('service'),
            'timestamp': log_data.get('timestamp'),
            'insertId': log_data.get('insertId')
        },
        'createdAt': firestore.SERVER_TIMESTAMP
    })

    print(f"Generated embedding for log: {log_data.get('insertId')}")
```

Deploy:
```bash
cd functions/firebase
gcloud functions deploy generate-log-embedding \
  --gen2 \
  --runtime=python312 \
  --region=us-central1 \
  --source=. \
  --entry-point=generate_log_embedding \
  --trigger-topic=logging-critical-alerts \
  --service-account=glass-pane-firebase@diatonic-ai-gcp.iam.gserviceaccount.com
```

### Step 2: Add Enhanced AI Tools

Update `src/agent/tools/definitions.py` with new tools:
- `analyze_cost_tool` (see ENHANCEMENT_ANALYSIS.md)
- `detect_failures_tool`
- `optimize_code_tool`

## Phase 5: Testing & Validation

### Test Firebase Connection
```bash
# Create test session
curl -X POST https://glass-pane-<hash>.run.app/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"userId": "test-user", "title": "Test Session"}'

# List sessions
curl https://glass-pane-<hash>.run.app/api/sessions?userId=test-user
```

### Test Embedding Generation
```bash
# Publish test log to Pub/Sub
gcloud pubsub topics publish logging-critical-alerts \
  --message='{"severity":"ERROR","service":"test","message":"Test error"}'

# Check Firestore for embedding
firebase firestore:get embeddings
```

### Test Real-Time Updates
1. Open Glass Pane in two browser windows
2. Send chat message in one window
3. Verify message appears in real-time in second window

## Monitoring & Debugging

### View Firestore Data
```bash
# Open Firestore console
firebase open firestore

# Query data via CLI
firebase firestore:get sessions/<session-id>
```

### View Cloud Function Logs
```bash
gcloud functions logs read generate-log-embedding --limit=50
```

### Cost Monitoring
- Firestore: Console > Firestore > Usage
- Cloud Functions: Console > Cloud Functions > Metrics
- Vertex AI: Console > Vertex AI > Quotas

## Rollback Plan

If issues occur:

```bash
# Disable Firebase integration
gcloud run services update glass-pane \
  --set-env-vars FIREBASE_ENABLED=false

# Revert to previous revision
gcloud run services update-traffic glass-pane \
  --to-revisions=<previous-revision>=100
```

## Next Steps

1. Enable Firebase Authentication for user management
2. Implement cost analytics dashboard
3. Add optimization recommendation engine
4. Set up monitoring alerts for high Firestore usage
5. Implement data retention policies (auto-delete old sessions)

## Support

- Firebase Docs: https://firebase.google.com/docs
- Firestore Security Rules: https://firebase.google.com/docs/firestore/security/get-started
- Cloud Functions: https://cloud.google.com/functions/docs
