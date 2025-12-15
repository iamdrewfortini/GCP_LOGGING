/**
 * Firebase Authentication utilities with OAuth support.
 *
 * Supports:
 * - Google OAuth
 * - GitHub OAuth
 * - Email/Password
 * - Anonymous sign-in
 */

import {
  signInWithPopup,
  signInWithRedirect,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInAnonymously,
  signOut,
  onAuthStateChanged,
  GoogleAuthProvider,
  GithubAuthProvider,
  OAuthProvider,
  type User,
  type UserCredential,
} from "firebase/auth"
import { auth } from "./firebase"

// OAuth Providers
const googleProvider = new GoogleAuthProvider()
const githubProvider = new GithubAuthProvider()
const microsoftProvider = new OAuthProvider("microsoft.com")

// Configure Google provider
googleProvider.addScope("email")
googleProvider.addScope("profile")
googleProvider.setCustomParameters({
  prompt: "select_account",
})

// Configure GitHub provider
githubProvider.addScope("user:email")

// Configure Microsoft provider
microsoftProvider.addScope("email")
microsoftProvider.addScope("profile")

/**
 * Sign in with Google OAuth using popup.
 */
export async function signInWithGoogle(): Promise<UserCredential> {
  try {
    const result = await signInWithPopup(auth, googleProvider)
    console.log("Google sign-in successful:", result.user.email)
    return result
  } catch (error: any) {
    console.error("Google sign-in error:", error.code, error.message)
    throw error
  }
}

/**
 * Sign in with Google OAuth using redirect (better for mobile).
 */
export async function signInWithGoogleRedirect(): Promise<void> {
  await signInWithRedirect(auth, googleProvider)
}

/**
 * Sign in with GitHub OAuth using popup.
 */
export async function signInWithGitHub(): Promise<UserCredential> {
  try {
    const result = await signInWithPopup(auth, githubProvider)
    console.log("GitHub sign-in successful:", result.user.email)
    return result
  } catch (error: any) {
    console.error("GitHub sign-in error:", error.code, error.message)
    throw error
  }
}

/**
 * Sign in with Microsoft OAuth using popup.
 */
export async function signInWithMicrosoft(): Promise<UserCredential> {
  try {
    const result = await signInWithPopup(auth, microsoftProvider)
    console.log("Microsoft sign-in successful:", result.user.email)
    return result
  } catch (error: any) {
    console.error("Microsoft sign-in error:", error.code, error.message)
    throw error
  }
}

/**
 * Sign in with email and password.
 */
export async function signInWithEmail(
  email: string,
  password: string
): Promise<UserCredential> {
  try {
    const result = await signInWithEmailAndPassword(auth, email, password)
    console.log("Email sign-in successful:", result.user.email)
    return result
  } catch (error: any) {
    console.error("Email sign-in error:", error.code, error.message)
    throw error
  }
}

/**
 * Create a new account with email and password.
 */
export async function signUpWithEmail(
  email: string,
  password: string
): Promise<UserCredential> {
  try {
    const result = await createUserWithEmailAndPassword(auth, email, password)
    console.log("Account created:", result.user.email)
    return result
  } catch (error: any) {
    console.error("Sign-up error:", error.code, error.message)
    throw error
  }
}

/**
 * Sign in anonymously (for demo/testing).
 */
export async function signInAsGuest(): Promise<UserCredential> {
  try {
    const result = await signInAnonymously(auth)
    console.log("Anonymous sign-in successful:", result.user.uid)
    return result
  } catch (error: any) {
    console.error("Anonymous sign-in error:", error.code, error.message)
    throw error
  }
}

/**
 * Sign out the current user.
 */
export async function logout(): Promise<void> {
  try {
    await signOut(auth)
    console.log("Signed out successfully")
  } catch (error: any) {
    console.error("Sign-out error:", error.code, error.message)
    throw error
  }
}

/**
 * Subscribe to auth state changes.
 */
export function subscribeToAuthState(
  callback: (user: User | null) => void
): () => void {
  return onAuthStateChanged(auth, callback)
}

/**
 * Get the current user.
 */
export function getCurrentUser(): User | null {
  return auth.currentUser
}

/**
 * Get the current user's ID token for API calls.
 */
export async function getIdToken(forceRefresh = false): Promise<string | null> {
  const user = auth.currentUser
  if (!user) return null
  return user.getIdToken(forceRefresh)
}

/**
 * Auth error codes for user-friendly messages.
 */
export const AUTH_ERROR_MESSAGES: Record<string, string> = {
  "auth/invalid-email": "Invalid email address format.",
  "auth/user-disabled": "This account has been disabled.",
  "auth/user-not-found": "No account found with this email.",
  "auth/wrong-password": "Incorrect password.",
  "auth/email-already-in-use": "An account already exists with this email.",
  "auth/weak-password": "Password must be at least 6 characters.",
  "auth/popup-closed-by-user": "Sign-in popup was closed.",
  "auth/cancelled-popup-request": "Another popup is already open.",
  "auth/popup-blocked": "Sign-in popup was blocked by the browser.",
  "auth/account-exists-with-different-credential":
    "An account already exists with this email using a different sign-in method.",
  "auth/network-request-failed": "Network error. Please check your connection.",
  "auth/too-many-requests": "Too many failed attempts. Please try again later.",
  "auth/operation-not-allowed": "This sign-in method is not enabled.",
}

/**
 * Get a user-friendly error message.
 */
export function getAuthErrorMessage(error: any): string {
  const code = error?.code || ""
  return AUTH_ERROR_MESSAGES[code] || error?.message || "An error occurred."
}
