/**
 * Authentication Context for React.
 *
 * Provides authentication state and methods throughout the app.
 *
 * Usage:
 *   import { useAuth } from '@/contexts/AuthContext'
 *   const { user, signInWithGoogle, logout } = useAuth()
 */

import React, { createContext, useContext, useEffect, useState } from "react"
import type { User } from "firebase/auth"
import type { RecaptchaVerifier, ApplicationVerifier } from "firebase/auth"
import {
  subscribeToAuthState,
  signInWithGoogle,
  signInWithGitHub,
  signInWithMicrosoft,
  signInWithEmail,
  signUpWithEmail,
  signInAsGuest,
  logout as firebaseLogout,
  getIdToken,
  getAuthErrorMessage,
  setupRecaptchaVerifier,
  sendVerificationCode,
  verifyPhoneCode,
  clearPhoneVerification,
} from "@/lib/auth"

interface AuthContextType {
  // State
  user: User | null
  loading: boolean
  error: string | null
  phoneVerificationPending: boolean

  // Sign-in methods
  signInWithGoogle: () => Promise<void>
  signInWithGitHub: () => Promise<void>
  signInWithMicrosoft: () => Promise<void>
  signInWithEmail: (email: string, password: string) => Promise<void>
  signUpWithEmail: (email: string, password: string) => Promise<void>
  signInAsGuest: () => Promise<void>
  logout: () => Promise<void>

  // Phone authentication
  setupPhoneRecaptcha: (containerId: string, invisible?: boolean) => RecaptchaVerifier
  sendPhoneVerification: (phoneNumber: string, appVerifier: ApplicationVerifier) => Promise<void>
  verifyPhoneCode: (code: string) => Promise<void>
  cancelPhoneVerification: () => void

  // Utilities
  getIdToken: (forceRefresh?: boolean) => Promise<string | null>
  clearError: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

interface AuthProviderProps {
  children: React.ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [phoneVerificationPending, setPhoneVerificationPending] = useState(false)

  // Subscribe to auth state changes
  useEffect(() => {
    const unsubscribe = subscribeToAuthState((user) => {
      setUser(user)
      setLoading(false)
    })

    return () => unsubscribe()
  }, [])

  // Wrap auth methods with error handling
  const handleSignInWithGoogle = async () => {
    try {
      setError(null)
      setLoading(true)
      await signInWithGoogle()
    } catch (e) {
      setError(getAuthErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  const handleSignInWithGitHub = async () => {
    try {
      setError(null)
      setLoading(true)
      await signInWithGitHub()
    } catch (e) {
      setError(getAuthErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  const handleSignInWithMicrosoft = async () => {
    try {
      setError(null)
      setLoading(true)
      await signInWithMicrosoft()
    } catch (e) {
      setError(getAuthErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  const handleSignInWithEmail = async (email: string, password: string) => {
    try {
      setError(null)
      setLoading(true)
      await signInWithEmail(email, password)
    } catch (e) {
      setError(getAuthErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  const handleSignUpWithEmail = async (email: string, password: string) => {
    try {
      setError(null)
      setLoading(true)
      await signUpWithEmail(email, password)
    } catch (e) {
      setError(getAuthErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  const handleSignInAsGuest = async () => {
    try {
      setError(null)
      setLoading(true)
      await signInAsGuest()
    } catch (e) {
      setError(getAuthErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    try {
      setError(null)
      await firebaseLogout()
    } catch (e) {
      setError(getAuthErrorMessage(e))
    }
  }

  // Phone authentication handlers
  const handleSetupPhoneRecaptcha = (containerId: string, invisible = true): RecaptchaVerifier => {
    return setupRecaptchaVerifier(containerId, invisible)
  }

  const handleSendPhoneVerification = async (phoneNumber: string, appVerifier: ApplicationVerifier) => {
    try {
      setError(null)
      setLoading(true)
      await sendVerificationCode(phoneNumber, appVerifier)
      setPhoneVerificationPending(true)
    } catch (e) {
      setError(getAuthErrorMessage(e))
      throw e
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyPhoneCode = async (code: string) => {
    try {
      setError(null)
      setLoading(true)
      await verifyPhoneCode(code)
      setPhoneVerificationPending(false)
    } catch (e) {
      setError(getAuthErrorMessage(e))
      throw e
    } finally {
      setLoading(false)
    }
  }

  const handleCancelPhoneVerification = () => {
    clearPhoneVerification()
    setPhoneVerificationPending(false)
    setError(null)
  }

  const clearError = () => setError(null)

  const value: AuthContextType = {
    user,
    loading,
    error,
    phoneVerificationPending,
    signInWithGoogle: handleSignInWithGoogle,
    signInWithGitHub: handleSignInWithGitHub,
    signInWithMicrosoft: handleSignInWithMicrosoft,
    signInWithEmail: handleSignInWithEmail,
    signUpWithEmail: handleSignUpWithEmail,
    signInAsGuest: handleSignInAsGuest,
    logout: handleLogout,
    setupPhoneRecaptcha: handleSetupPhoneRecaptcha,
    sendPhoneVerification: handleSendPhoneVerification,
    verifyPhoneCode: handleVerifyPhoneCode,
    cancelPhoneVerification: handleCancelPhoneVerification,
    getIdToken,
    clearError,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}
