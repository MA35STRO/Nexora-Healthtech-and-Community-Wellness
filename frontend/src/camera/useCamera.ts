// Browser perception: opens THIS device's webcam automatically, runs MediaPipe Pose locally,
// draws the skeleton, and streams only 33 landmark points per frame to the backend.
// Video frames never leave the browser (except a single photo when the user taps "Check my medicine").
import { FilesetResolver, PoseLandmarker } from '@mediapipe/tasks-vision'
import { useCallback, useEffect, useRef, useState } from 'react'
import { wsUrl } from '../api'
import { motionScore, pack, SKELETON, shouldProcess, VISIBLE, type Packed } from './poseMath'

const FPS = 15
const LOCAL_MODEL = '/mediapipe/pose_landmarker_lite.task'
const CDN_MODEL =
  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task'

export type CamStatus = 'starting' | 'loading-model' | 'live' | 'denied' | 'no-camera' | 'error'

export interface ServerView {
  person: boolean
  posture: string
  torso_angle: number
  full_body: boolean
  state: string
}

async function createLandmarker(): Promise<PoseLandmarker> {
  const fileset = await FilesetResolver.forVisionTasks('/mediapipe/wasm')
  const attempt = (modelAssetPath: string, delegate: 'GPU' | 'CPU') =>
    PoseLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath, delegate },
      runningMode: 'VIDEO',
      numPoses: 1,
    })
  for (const [path, delegate] of [
    [LOCAL_MODEL, 'GPU'],
    [LOCAL_MODEL, 'CPU'],
    [CDN_MODEL, 'CPU'],
  ] as const) {
    try {
      return await attempt(path, delegate)
    } catch (e) {
      console.warn(`Pose model (${delegate}, ${path}) failed`, e)
    }
  }
  throw new Error('Could not load the pose model')
}

export function useCamera(privacy: boolean) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [status, setStatus] = useState<CamStatus>('starting')
  const [error, setError] = useState<string | null>(null)
  const [server, setServer] = useState<ServerView | null>(null)
  const [fps, setFps] = useState(0)
  const privacyRef = useRef(privacy)
  privacyRef.current = privacy

  useEffect(() => {
    let stopped = false
    let stream: MediaStream | null = null
    let landmarker: PoseLandmarker | null = null
    let ws: WebSocket | null = null
    let raf = 0
    let wsTimer: ReturnType<typeof setTimeout> | undefined

    const connect = () => {
      if (stopped) return
      ws = new WebSocket(wsUrl('/ws/perception'))
      ws.onmessage = (e) => setServer(JSON.parse(e.data) as ServerView)
      ws.onclose = () => {
        if (!stopped) wsTimer = setTimeout(connect, 1500)
      }
      ws.onerror = () => ws?.close()
    }

    const start = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setStatus('no-camera')
        setError('This browser cannot access a camera (needs Chrome/Edge on localhost or HTTPS).')
        return
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
          audio: false,
        })
      } catch (e) {
        const name = (e as DOMException).name
        setStatus(name === 'NotAllowedError' ? 'denied' : 'no-camera')
        setError(
          name === 'NotAllowedError' ? 'Camera permission was denied.' : 'No camera found on this device.',
        )
        return
      }
      if (stopped) return stream.getTracks().forEach((t) => t.stop())
      const video = videoRef.current!
      video.srcObject = stream
      await video.play().catch(() => undefined)
      setStatus('loading-model')
      try {
        landmarker = await createLandmarker()
      } catch (e) {
        setStatus('error')
        setError(String(e))
        return
      }
      if (stopped) return
      setStatus('live')
      connect()

      let last = 0
      let prev: Packed | null = null
      let frames = 0
      let fpsT = performance.now()
      const loop = () => {
        if (stopped) return
        raf = requestAnimationFrame(loop)
        const now = performance.now()
        if (!shouldProcess(now, last, FPS) || video.readyState < 2) return
        last = now
        const result = landmarker!.detectForVideo(video, now)
        const lms = result.landmarks?.[0]
        const packed = lms ? pack(lms) : null
        const motion = packed ? motionScore(prev, packed) : null
        prev = packed
        draw(canvasRef.current, video, packed, privacyRef.current)
        if (ws?.readyState === WebSocket.OPEN && ws.bufferedAmount < 64_000) {
          ws.send(JSON.stringify({ lm: packed, motion }))
        }
        frames++
        if (now - fpsT >= 1000) {
          setFps(Math.round((frames * 1000) / (now - fpsT)))
          frames = 0
          fpsT = now
        }
      }
      loop()
    }
    start()

    return () => {
      stopped = true
      cancelAnimationFrame(raf)
      clearTimeout(wsTimer)
      ws?.close()
      landmarker?.close()
      stream?.getTracks().forEach((t) => t.stop())
    }
  }, [])

  /** One JPEG of the current frame — used ONLY when the user taps "Check my medicine". */
  const captureFrame = useCallback((): string | null => {
    const v = videoRef.current
    if (!v || v.readyState < 2) return null
    const c = document.createElement('canvas')
    c.width = v.videoWidth
    c.height = v.videoHeight
    c.getContext('2d')!.drawImage(v, 0, 0)
    return c.toDataURL('image/jpeg', 0.85)
  }, [])

  return { videoRef, canvasRef, status, error, server, fps, captureFrame }
}

function draw(
  canvas: HTMLCanvasElement | null,
  video: HTMLVideoElement,
  pts: Packed | null,
  privacy: boolean,
) {
  if (!canvas) return
  const w = video.videoWidth || 640
  const h = video.videoHeight || 480
  if (canvas.width !== w) canvas.width = w
  if (canvas.height !== h) canvas.height = h
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, w, h)
  if (privacy) {
    ctx.fillStyle = '#0f2a2e'
    ctx.fillRect(0, 0, w, h)
  }
  if (!pts) return
  ctx.lineWidth = 5
  ctx.lineCap = 'round'
  ctx.strokeStyle = privacy ? '#7fe3d0' : 'rgba(127, 227, 208, 0.9)'
  for (const [a, b] of SKELETON) {
    const pa = pts[a]
    const pb = pts[b]
    if (!pa || !pb || pa[2] < VISIBLE || pb[2] < VISIBLE) continue
    ctx.beginPath()
    ctx.moveTo(pa[0] * w, pa[1] * h)
    ctx.lineTo(pb[0] * w, pb[1] * h)
    ctx.stroke()
  }
  ctx.fillStyle = '#ffffff'
  for (const i of [0, 11, 12, 23, 24, 25, 26, 27, 28]) {
    const p = pts[i]
    if (p && p[2] >= VISIBLE) {
      ctx.beginPath()
      ctx.arc(p[0] * w, p[1] * h, 6, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}
