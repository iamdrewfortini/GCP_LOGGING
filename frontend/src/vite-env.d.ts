/// <reference types="vite/client" />

interface ImportMetaEnv {
  // API Configuration
  readonly VITE_API_URL: string

  // Firebase Configuration
  readonly VITE_USE_FIREBASE_EMULATORS: string
  readonly VITE_FIREBASE_API_KEY: string
  readonly VITE_FIREBASE_AUTH_DOMAIN: string
  readonly VITE_FIREBASE_PROJECT_ID: string
  readonly VITE_FIREBASE_STORAGE_BUCKET: string
  readonly VITE_FIREBASE_MESSAGING_SENDER_ID: string
  readonly VITE_FIREBASE_APP_ID: string

  // Emulator Configuration
  readonly VITE_FIREBASE_AUTH_EMULATOR_HOST: string
  readonly VITE_FIREBASE_AUTH_EMULATOR_PORT: string
  readonly VITE_FIREBASE_FIRESTORE_EMULATOR_HOST: string
  readonly VITE_FIREBASE_FIRESTORE_EMULATOR_PORT: string
  readonly VITE_FIREBASE_STORAGE_EMULATOR_HOST: string
  readonly VITE_FIREBASE_STORAGE_EMULATOR_PORT: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
