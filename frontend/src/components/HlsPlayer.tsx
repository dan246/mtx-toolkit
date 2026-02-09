import { useRef, useEffect, useState, useCallback } from 'react'
import Hls from 'hls.js'
import { Loader2, AlertCircle, Volume2, VolumeX } from 'lucide-react'
import { healthApi } from '../services/api'
import type { PlaybackIssue } from '../types'

interface HlsPlayerProps {
  src: string
  autoPlay?: boolean
  muted?: boolean
  controls?: boolean
  className?: string
  onError?: (error: string) => void
  onReady?: () => void
  poster?: string
  // Phase 4: Watchdog props
  streamId?: number
  enableWatchdog?: boolean
  onPlaybackIssue?: (issue: PlaybackIssue) => void
}

export default function HlsPlayer({
  src,
  autoPlay = true,
  muted = true,
  controls = true,
  className = '',
  onError,
  onReady,
  poster,
  streamId,
  enableWatchdog = true,
  onPlaybackIssue,
}: HlsPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const hlsRef = useRef<Hls | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isMuted, setIsMuted] = useState(muted)

  // Watchdog state refs (to avoid stale closures in setInterval)
  const lastTimeRef = useRef<number>(0)
  const stallCountRef = useRef<number>(0)
  const stallStartRef = useRef<number | null>(null)
  const clientIdRef = useRef<string>(
    `client-${Math.random().toString(36).substring(2, 10)}`
  )

  const reportIssue = useCallback(
    (action: 'seek_nudge' | 'level_switch' | 'full_reload', stallDurationMs: number) => {
      const issue: PlaybackIssue = {
        type: 'stall',
        duration_ms: stallDurationMs,
        action,
      }
      onPlaybackIssue?.(issue)

      // Report to backend
      if (streamId) {
        healthApi.submitPlaybackReport({
          stream_id: streamId,
          client_id: clientIdRef.current,
          stall_count: stallCountRef.current,
          stall_duration_ms: stallDurationMs,
          recovery_action: action,
        }).catch(() => {
          // Silently ignore report failures
        })
      }
    },
    [streamId, onPlaybackIssue]
  )

  useEffect(() => {
    const video = videoRef.current
    if (!video || !src) return

    setIsLoading(true)
    setError(null)
    stallCountRef.current = 0
    stallStartRef.current = null

    // Clean up previous instance
    if (hlsRef.current) {
      hlsRef.current.destroy()
      hlsRef.current = null
    }

    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
        backBufferLength: 90,
        maxBufferLength: 30,
        maxMaxBufferLength: 600,
        liveSyncDurationCount: 3,
        liveMaxLatencyDurationCount: 10,
      })

      hlsRef.current = hls

      hls.loadSource(src)
      hls.attachMedia(video)

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setIsLoading(false)
        if (autoPlay) {
          video.play().catch(() => {
            // Autoplay blocked, that's okay
          })
        }
        onReady?.()
      })

      hls.on(Hls.Events.ERROR, (_, data) => {
        if (data.fatal) {
          let errorMsg = 'Stream unavailable'
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              errorMsg = 'Network error - stream may not be active'
              break
            case Hls.ErrorTypes.MEDIA_ERROR:
              errorMsg = 'Media error - incompatible format'
              hls.recoverMediaError()
              return
            default:
              errorMsg = `Stream error: ${data.details}`
          }
          setError(errorMsg)
          setIsLoading(false)
          onError?.(errorMsg)
        }
      })
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      // Native HLS support (Safari)
      video.src = src
      video.addEventListener('loadedmetadata', () => {
        setIsLoading(false)
        if (autoPlay) {
          video.play().catch(() => {})
        }
        onReady?.()
      })
      video.addEventListener('error', () => {
        const errorMsg = 'Failed to load stream'
        setError(errorMsg)
        setIsLoading(false)
        onError?.(errorMsg)
      })
    } else {
      const errorMsg = 'HLS is not supported in this browser'
      setError(errorMsg)
      setIsLoading(false)
      onError?.(errorMsg)
    }

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy()
        hlsRef.current = null
      }
    }
  }, [src, autoPlay, onError, onReady])

  // Phase 4: Watchdog effect
  useEffect(() => {
    if (!enableWatchdog || !videoRef.current) return

    const watchdogInterval = setInterval(() => {
      const video = videoRef.current
      const hls = hlsRef.current
      if (!video || video.paused || isLoading || error) return

      const currentTime = video.currentTime

      // Stall detection: currentTime not advancing
      if (currentTime === lastTimeRef.current && currentTime > 0) {
        if (stallStartRef.current === null) {
          stallStartRef.current = Date.now()
        }

        const stallDuration = Date.now() - stallStartRef.current
        stallCountRef.current++

        if (stallDuration > 30000 && hls) {
          // 30s stall: full reload
          reportIssue('full_reload', stallDuration)
          hls.destroy()
          hlsRef.current = null
          const newHls = new Hls({
            enableWorker: true,
            lowLatencyMode: true,
            backBufferLength: 90,
            liveSyncDurationCount: 3,
          })
          hlsRef.current = newHls
          newHls.loadSource(src)
          newHls.attachMedia(video)
          stallStartRef.current = null
        } else if (stallDuration > 20000 && hls) {
          // 20s stall: level switch (drop quality)
          if (hls.currentLevel > 0) {
            reportIssue('level_switch', stallDuration)
            hls.currentLevel = hls.currentLevel - 1
          }
        } else if (stallDuration > 10000) {
          // 10s stall: seek nudge
          reportIssue('seek_nudge', stallDuration)
          video.currentTime = video.currentTime + 0.1
        }
      } else {
        // Playing normally, reset stall tracking
        stallStartRef.current = null
      }

      lastTimeRef.current = currentTime

      // Frame quality check
      if ('getVideoPlaybackQuality' in video) {
        const quality = video.getVideoPlaybackQuality()
        if (quality.totalVideoFrames > 0) {
          const dropRate = quality.droppedVideoFrames / quality.totalVideoFrames
          if (dropRate > 0.05 && streamId) {
            // >5% dropped frames
            healthApi.submitPlaybackReport({
              stream_id: streamId,
              client_id: clientIdRef.current,
              frames_decoded: quality.totalVideoFrames,
              frames_dropped: quality.droppedVideoFrames,
            }).catch(() => {})
          }
        }
      }
    }, 2000)

    return () => clearInterval(watchdogInterval)
  }, [enableWatchdog, isLoading, error, streamId, src, reportIssue])

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.muted = isMuted
    }
  }, [isMuted])

  const toggleMute = () => {
    setIsMuted(!isMuted)
  }

  return (
    <div className={`relative bg-black ${className}`}>
      <video
        ref={videoRef}
        className="w-full h-full object-contain"
        muted={isMuted}
        playsInline
        controls={controls && !isLoading && !error}
        poster={poster}
      />

      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/50">
          <div className="flex flex-col items-center gap-2 text-white">
            <Loader2 className="w-8 h-8 animate-spin" />
            <span className="text-sm">Loading stream...</span>
          </div>
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/80">
          <div className="flex flex-col items-center gap-2 text-white text-center p-4">
            <AlertCircle className="w-8 h-8 text-red-400" />
            <span className="text-sm">{error}</span>
          </div>
        </div>
      )}

      {/* Mute toggle button (when no controls) */}
      {!controls && !isLoading && !error && (
        <button
          onClick={toggleMute}
          className="absolute bottom-2 right-2 p-1.5 bg-black/60 rounded-full text-white hover:bg-black/80 transition-colors"
        >
          {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
        </button>
      )}
    </div>
  )
}
