// Copies the MediaPipe WASM runtime and pose model into public/ so the app works fully offline.
import { cpSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const wasmSrc = resolve(root, 'node_modules/@mediapipe/tasks-vision/wasm')
const modelSrc = resolve(root, 'models/pose_landmarker_lite.task')

mkdirSync(resolve(root, 'public/mediapipe'), { recursive: true })
cpSync(wasmSrc, resolve(root, 'public/mediapipe/wasm'), { recursive: true })
if (existsSync(modelSrc)) {
  cpSync(modelSrc, resolve(root, 'public/mediapipe/pose_landmarker_lite.task'))
} else {
  console.warn('Pose model not found at', modelSrc, '- the app will download it from the MediaPipe CDN.')
}
console.log('MediaPipe assets copied to public/mediapipe')
