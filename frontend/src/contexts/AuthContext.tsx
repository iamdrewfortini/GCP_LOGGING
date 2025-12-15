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
} from "@/lib/auth"

interface AuthContextType {
  // State
  user: User | null
  loading: boolean
  error: string | null

  // Sign-in methods
  signInWithGoogle: () => Promise<void>
  signInWithGitHub: () => Promise<void>
  signInWithMicrosoft: () => Promise<void>
  signInWithEmail: (email: string, password: string) => Promise<void>
  signUpWithEmail: (email: string, password: string) => Promise<void>
  signInAsGuest: () => Promise<void>
  logout: () => Promise<void>

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

  const clearError = () => setError(null)

  const value: AuthContextType = {
    user,
    loading,
    error,
    signInWithGoogle: handleSignInWithGoogle,
    signInWithGitHub: handleSignInWithGitHub,
    signInWithMicrosoft: handleSignInWithMicrosoft,
    signInWithEmail: handleSignInWithEmail,
    signUpWithEmail: handleSignUpWithEmail,
    signInAsGuest: handleSignInAsGuest,
    logout: handleLogout,
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
