import { useState, useEffect } from "react"
import { useAuth } from "@/contexts/AuthContext"
import { cn } from "@/lib/utils"

// Cryptic glitch characters
const GLITCH_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?/~`"

function GlitchText({ text, className }: { text: string; className?: string }) {
  const [displayText, setDisplayText] = useState(text)
  const [isGlitching, setIsGlitching] = useState(false)

  useEffect(() => {
    if (!isGlitching) return

    let iterations = 0
    const interval = setInterval(() => {
      setDisplayText(
        text
          .split("")
          .map((char, index) => {
            if (index < iterations) return text[index]
            if (char === " ") return " "
            return GLITCH_CHARS[Math.floor(Math.random() * GLITCH_CHARS.length)]
          })
          .join("")
      )

      if (iterations >= text.length) {
        clearInterval(interval)
        setIsGlitching(false)
      }
      iterations += 1 / 3
    }, 30)

    return () => clearInterval(interval)
  }, [isGlitching, text])

  useEffect(() => {
    const glitchInterval = setInterval(() => {
      if (Math.random() > 0.7) {
        setIsGlitching(true)
      }
    }, 3000)

    return () => clearInterval(glitchInterval)
  }, [])

  return <span className={className}>{displayText}</span>
}

function StaticNoise() {
  return (
    <div className="pointer-events-none fixed inset-0 z-0 opacity-[0.015]">
      <svg className="h-full w-full">
        <filter id="noise">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.8"
            numOctaves="4"
            stitchTiles="stitch"
          />
        </filter>
        <rect width="100%" height="100%" filter="url(#noise)" />
      </svg>
    </div>
  )
}

function ScanLines() {
  return (
    <div
      className="pointer-events-none fixed inset-0 z-0 opacity-[0.03]"
      style={{
        backgroundImage:
          "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 0, 0, 0.3) 2px, rgba(0, 0, 0, 0.3) 4px)",
      }}
    />
  )
}

export function LoginScreen() {
  const { signInWithGoogle, loading, error } = useAuth()
  const [hovered, setHovered] = useState(false)

  return (
    <div className="relative min-h-screen bg-black text-white overflow-hidden flex items-center justify-center">
      <StaticNoise />
      <ScanLines />

      {/* Ambient glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-white/[0.02] rounded-full blur-[100px]" />

      {/* Main content */}
      <div className="relative z-10 flex flex-col items-center space-y-12">
        {/* Logo/Title */}
        <div className="text-center space-y-2">
          <h1 className="text-6xl font-mono font-light tracking-[0.3em] text-white/90">
            <GlitchText text="DIATONIC" />
          </h1>
          <div className="h-px w-32 mx-auto bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <p className="text-xs tracking-[0.5em] text-white/30 font-mono uppercase">
            AI Systems
          </p>
        </div>

        {/* Status indicator */}
        <div className="flex items-center space-x-3 text-white/20 font-mono text-xs">
          <div className="w-1.5 h-1.5 rounded-full bg-white/30 animate-pulse" />
          <span className="tracking-widest">AWAITING AUTHENTICATION</span>
        </div>

        {/* Login button */}
        <button
          onClick={signInWithGoogle}
          disabled={loading}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          className={cn(
            "group relative px-12 py-4 border border-white/10 bg-white/[0.02]",
            "font-mono text-sm tracking-[0.2em] text-white/60",
            "transition-all duration-500 ease-out",
            "hover:border-white/30 hover:bg-white/[0.05] hover:text-white/90",
            "focus:outline-none focus:ring-1 focus:ring-white/20",
            "disabled:opacity-30 disabled:cursor-not-allowed"
          )}
        >
          {/* Button glow effect */}
          <div
            className={cn(
              "absolute inset-0 bg-white/5 blur-xl transition-opacity duration-500",
              hovered ? "opacity-100" : "opacity-0"
            )}
          />

          <span className="relative z-10">
            {loading ? (
              <span className="flex items-center space-x-3">
                <span className="w-4 h-4 border border-white/30 border-t-transparent rounded-full animate-spin" />
                <span>CONNECTING</span>
              </span>
            ) : (
              "INITIALIZE"
            )}
          </span>

          {/* Corner accents */}
          <div className="absolute top-0 left-0 w-2 h-2 border-t border-l border-white/20" />
          <div className="absolute top-0 right-0 w-2 h-2 border-t border-r border-white/20" />
          <div className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-white/20" />
          <div className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-white/20" />
        </button>

        {/* Error message */}
        {error && (
          <div className="font-mono text-xs text-red-400/60 tracking-wider animate-pulse">
            ERR: {error.toUpperCase()}
          </div>
        )}

        {/* Cryptic footer */}
        <div className="absolute bottom-8 left-0 right-0 text-center">
          <p className="font-mono text-[10px] text-white/10 tracking-[0.3em]">
            v0.0.1 // CLASSIFIED // INTERNAL USE ONLY
          </p>
        </div>
      </div>

      {/* Decorative elements */}
      <div className="absolute top-8 left-8 font-mono text-[10px] text-white/10">
        <div>SYS.INIT</div>
        <div className="mt-1">AUTH.PENDING</div>
      </div>

      <div className="absolute top-8 right-8 font-mono text-[10px] text-white/10 text-right">
        <div>{new Date().toISOString().split("T")[0]}</div>
        <div className="mt-1">NODE.PRIMARY</div>
      </div>

      <div className="absolute bottom-8 left-8 font-mono text-[10px] text-white/10">
        <div>SECTOR.07</div>
      </div>

      <div className="absolute bottom-8 right-8 font-mono text-[10px] text-white/10">
        <div>CLEARANCE.REQ</div>
      </div>
    </div>
  )
}
