/**
 * Firebase configuration with emulator support for local development.
 *
 * Environment variables:
 * - VITE_USE_FIREBASE_EMULATORS: Set to "true" to use local emulators
 * - VITE_FIREBASE_* : Firebase project configuration
 */

import { initializeApp, getApps, type FirebaseApp } from "firebase/app"
import { getAuth, connectAuthEmulator, type Auth } from "firebase/auth"
import { getFirestore, connectFirestoreEmulator, type Firestore } from "firebase/firestore"
import { getStorage, connectStorageEmulator, type FirebaseStorage } from "firebase/storage"

// Firebase configuration
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "demo-api-key",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "diatonic-ai-gcp.firebaseapp.com",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "diatonic-ai-gcp",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "diatonic-ai-gcp.appspot.com",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "",
}

// Emulator configuration
const emulatorConfig = {
  useEmulators: import.meta.env.VITE_USE_FIREBASE_EMULATORS === "true",
  authHost: import.meta.env.VITE_FIREBASE_AUTH_EMULATOR_HOST || "localhost",
  authPort: parseInt(import.meta.env.VITE_FIREBASE_AUTH_EMULATOR_PORT || "9099"),
  firestoreHost: import.meta.env.VITE_FIREBASE_FIRESTORE_EMULATOR_HOST || "localhost",
  firestorePort: parseInt(import.meta.env.VITE_FIREBASE_FIRESTORE_EMULATOR_PORT || "8181"),
  storageHost: import.meta.env.VITE_FIREBASE_STORAGE_EMULATOR_HOST || "localhost",
  storagePort: parseInt(import.meta.env.VITE_FIREBASE_STORAGE_EMULATOR_PORT || "9199"),
}

// Initialize Firebase app (singleton)
let app: FirebaseApp
let auth: Auth
let db: Firestore
let storage: FirebaseStorage
let emulatorsConnected = false

function initializeFirebase(): FirebaseApp {
  if (getApps().length === 0) {
    app = initializeApp(firebaseConfig)
    console.log("🔥 Firebase initialized with project:", firebaseConfig.projectId)
  } else {
    app = getApps()[0]
  }
  return app
}

function connectEmulators(): void {
  if (emulatorsConnected || !emulatorConfig.useEmulators) {
    return
  }

  console.log("🔥 Connecting to Firebase emulators...")

  // Connect Auth emulator
  try {
    connectAuthEmulator(auth, `http://${emulatorConfig.authHost}:${emulatorConfig.authPort}`, {
      disableWarnings: true,
    })
    console.log(`  ✓ Auth emulator: ${emulatorConfig.authHost}:${emulatorConfig.authPort}`)
  } catch (e) {
    console.warn("  ⚠ Auth emulator already connected or error:", e)
  }

  // Connect Firestore emulator
  try {
    connectFirestoreEmulator(db, emulatorConfig.firestoreHost, emulatorConfig.firestorePort)
    console.log(`  ✓ Firestore emulator: ${emulatorConfig.firestoreHost}:${emulatorConfig.firestorePort}`)
  } catch (e) {
    console.warn("  ⚠ Firestore emulator already connected or error:", e)
  }

  // Connect Storage emulator
  try {
    connectStorageEmulator(storage, emulatorConfig.storageHost, emulatorConfig.storagePort)
    console.log(`  ✓ Storage emulator: ${emulatorConfig.storageHost}:${emulatorConfig.storagePort}`)
  } catch (e) {
    console.warn("  ⚠ Storage emulator already connected or error:", e)
  }

  emulatorsConnected = true
}

// Initialize on module load
app = initializeFirebase()
auth = getAuth(app)
db = getFirestore(app)
storage = getStorage(app)

// Connect to emulators if configured
if (emulatorConfig.useEmulators) {
  connectEmulators()
} else {
  console.log("🔥 Using production Firebase services")
}

// Export initialized instances
export { app, auth, db, storage }

// Export config for debugging
export const isUsingEmulators = emulatorConfig.useEmulators
export const getFirebaseConfig = () => ({
  ...firebaseConfig,
  emulators: emulatorConfig,
})
