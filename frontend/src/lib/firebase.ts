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

const firebaseDebug = import.meta.env.DEV || import.meta.env.VITE_FIREBASE_DEBUG === "true"

function isLocalhost(): boolean {
  if (typeof window === "undefined") return false
  return window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
}

// Emulator configuration
// Rules:
// - If VITE_USE_FIREBASE_EMULATORS is explicitly set, honor it.
// - Otherwise, default to emulators in local dev on localhost to reduce accidental prod writes.
const emulatorFlag = import.meta.env.VITE_USE_FIREBASE_EMULATORS
const emulatorConfig = {
  useEmulators:
    emulatorFlag === "true" ||
    (emulatorFlag !== "false" && import.meta.env.DEV && isLocalhost()),
  authHost: import.meta.env.VITE_FIREBASE_AUTH_EMULATOR_HOST || "localhost",
  authPort: parseInt(import.meta.env.VITE_FIREBASE_AUTH_EMULATOR_PORT || "9099"),
  firestoreHost: import.meta.env.VITE_FIREBASE_FIRESTORE_EMULATOR_HOST || "localhost",
  firestorePort: parseInt(import.meta.env.VITE_FIREBASE_FIRESTORE_EMULATOR_PORT || "8181"),
  storageHost: import.meta.env.VITE_FIREBASE_STORAGE_EMULATOR_HOST || "localhost",
  storagePort: parseInt(import.meta.env.VITE_FIREBASE_STORAGE_EMULATOR_PORT || "9199"),
}

let emulatorsConnected = false

function initializeFirebase(): FirebaseApp {
  if (getApps().length === 0) {
    const app = initializeApp(firebaseConfig)
    if (firebaseDebug) {
      console.log("🔥 Firebase initialized with project:", firebaseConfig.projectId)
    }
    return app
  }
  return getApps()[0]
}

function connectEmulators(auth: Auth, db: Firestore, storage: FirebaseStorage): void {
  if (emulatorsConnected || !emulatorConfig.useEmulators) {
    return
  }

  if (firebaseDebug) {
    console.log("🔥 Connecting to Firebase emulators...")
  }

  // Connect Auth emulator
  try {
    connectAuthEmulator(auth, `http://${emulatorConfig.authHost}:${emulatorConfig.authPort}`, {
      disableWarnings: true,
    })
    if (firebaseDebug) {
      console.log(`  ✓ Auth emulator: ${emulatorConfig.authHost}:${emulatorConfig.authPort}`)
    }
  } catch (e) {
    if (firebaseDebug) {
      console.warn("  ⚠ Auth emulator already connected or error:", e)
    }
  }

  // Connect Firestore emulator
  try {
    connectFirestoreEmulator(db, emulatorConfig.firestoreHost, emulatorConfig.firestorePort)
    if (firebaseDebug) {
      console.log(`  ✓ Firestore emulator: ${emulatorConfig.firestoreHost}:${emulatorConfig.firestorePort}`)
    }
  } catch (e) {
    if (firebaseDebug) {
      console.warn("  ⚠ Firestore emulator already connected or error:", e)
    }
  }

  // Connect Storage emulator
  try {
    connectStorageEmulator(storage, emulatorConfig.storageHost, emulatorConfig.storagePort)
    if (firebaseDebug) {
      console.log(`  ✓ Storage emulator: ${emulatorConfig.storageHost}:${emulatorConfig.storagePort}`)
    }
  } catch (e) {
    if (firebaseDebug) {
      console.warn("  ⚠ Storage emulator already connected or error:", e)
    }
  }

  emulatorsConnected = true
}

// Initialize on module load
export const app = initializeFirebase()
export const auth = getAuth(app)
export const db = getFirestore(app)
export const storage = getStorage(app)

// Connect to emulators if configured
if (emulatorConfig.useEmulators) {
  connectEmulators(auth, db, storage)
} else {
  if (firebaseDebug) {
    console.log("🔥 Using production Firebase services")
  }
}

// Export config for debugging
export const isUsingEmulators = emulatorConfig.useEmulators
export const getFirebaseConfig = () => ({
  ...firebaseConfig,
  emulators: emulatorConfig,
})
