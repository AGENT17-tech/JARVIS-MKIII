import { useRef, useEffect } from 'react'
import * as THREE from 'three'

// ── Constants ──────────────────────────────────────────────────────────────────
const GLOBE_R       = 240
const TILT_RAD      = 23.5 * Math.PI / 180
const BASE_SPEED    = 0.0008
const MAX_TRAVELERS = 100
const MID_COUNT     = 70
const EDGE_COUNT    = 320

// ── Helpers ────────────────────────────────────────────────────────────────────
const toRad = d => d * Math.PI / 180
const ll2v  = (lat, lon, r = GLOBE_R) => new THREE.Vector3(
  r * Math.cos(toRad(lat)) * Math.cos(toRad(lon)),
  r * Math.sin(toRad(lat)),
  r * Math.cos(toRad(lat)) * Math.sin(toRad(lon)),
)

const adaptLift = (a, b, base) => {
  const dot = a.clone().normalize().dot(b.clone().normalize())
  return base + GLOBE_R * 0.45 * Math.max(0, -dot)
}

const makeArcPts = (a, b, lift, segs = 20) => {
  const cp = a.clone().add(b).multiplyScalar(0.5).normalize().multiplyScalar(GLOBE_R + lift)
  return new THREE.QuadraticBezierCurve3(a.clone(), cp, b.clone()).getPoints(segs)
}

const buildLineSegs = (parent, ptArrays, color, opacity, depthTest = true) => {
  if (!ptArrays.length) return null
  const verts = []
  ptArrays.forEach(pts => {
    for (let i = 0; i < pts.length - 1; i++) verts.push(pts[i], pts[i + 1])
  })
  const geo = new THREE.BufferGeometry().setFromPoints(verts)
  const mat = new THREE.LineBasicMaterial({
    color, transparent: true, opacity,
    blending: THREE.AdditiveBlending, depthWrite: false, depthTest,
  })
  const ls = new THREE.LineSegments(geo, mat)
  parent.add(ls)
  return ls
}

// ── Hub city lat/lon ───────────────────────────────────────────────────────────
const HUB_LL = [
  [40.7,  -74.0],  // New York
  [51.5,   -0.1],  // London
  [55.7,   37.6],  // Moscow
  [39.9,  116.4],  // Beijing
  [35.7,  139.7],  // Tokyo
  [19.1,   72.9],  // Mumbai
  [25.2,   55.3],  // Dubai
  [ 1.4,  103.8],  // Singapore
  [37.6,  126.9],  // Seoul
  [48.9,    2.3],  // Paris
  [34.0, -118.2],  // Los Angeles
  [-1.3,   36.8],  // Nairobi
]

const randPopLL = () => {
  const r = Math.random()
  if      (r < 0.20) return [25 + Math.random()*25, -120 + Math.random()*50]
  else if (r < 0.40) return [44 + Math.random()*14,  -12 + Math.random()*42]
  else if (r < 0.62) return [20 + Math.random()*26,  100 + Math.random()*46]
  else if (r < 0.77) return [10 + Math.random()*22,   65 + Math.random()*26]
  else if (r < 0.88) return [18 + Math.random()*18,   35 + Math.random()*26]
  else return [-50 + Math.random()*100, -180 + Math.random()*360]
}

// ── Component ──────────────────────────────────────────────────────────────────
export default function GlobeNetwork({ isSpeaking, isThinking }) {
  const mountRef = useRef(null)
  const speakRef = useRef(isSpeaking)
  const thinkRef = useRef(isThinking)
  useEffect(() => { speakRef.current = isSpeaking }, [isSpeaking])
  useEffect(() => { thinkRef.current = isThinking }, [isThinking])

  useEffect(() => {
    const el = mountRef.current
    if (!el) return

    const W = () => el.clientWidth  || 800
    const H = () => el.clientHeight || 600

    // ── Renderer ───────────────────────────────────────────────────────────
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    renderer.setSize(W(), H())
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x010d1a, 1)
    const canvas = renderer.domElement
    canvas.style.display = 'block'
    el.appendChild(canvas)

    const scene  = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(45, W() / H(), 1, 6000)
    const camDist = 680
    camera.position.set(0, camDist * Math.sin(toRad(15)), camDist * Math.cos(toRad(15)))
    camera.lookAt(0, 0, 0)

    // ── Lights ─────────────────────────────────────────────────────────────
    scene.add(new THREE.AmbientLight(0x333333))
    const dirLight = new THREE.DirectionalLight(0x4488ff, 0.6)
    dirLight.position.set(-1, 1, 0.5).normalize()
    scene.add(dirLight)

    // ── Globe group ────────────────────────────────────────────────────────
    const group = new THREE.Group()
    group.rotation.z = TILT_RAD
    scene.add(group)

    // Earth-textured sphere
    const earthTexture = new THREE.TextureLoader().load(
      'https://unpkg.com/three-globe/example/img/earth-dark.jpg',
    )
    group.add(new THREE.Mesh(
      new THREE.SphereGeometry(GLOBE_R, 64, 64),
      new THREE.MeshPhongMaterial({
        map: earthTexture,
        specular: new THREE.Color(0x112244),
        shininess: 12,
      }),
    ))

    // ── Lat/lon wireframe grid ─────────────────────────────────────────────
    {
      const SEGS = 64, pts = []
      const push = (lat, lon) => pts.push(ll2v(lat, lon, GLOBE_R + 0.8))
      for (let lat = -80; lat <= 80; lat += 10)
        for (let s = 0; s <= SEGS; s++) {
          const lon = -180 + 360 / SEGS * s
          push(lat, lon); if (s > 0 && s < SEGS) push(lat, lon)
        }
      for (let lon = -180; lon < 180; lon += 10)
        for (let s = 0; s <= SEGS; s++) {
          const lat = -90 + 180 / SEGS * s
          push(lat, lon); if (s > 0 && s < SEGS) push(lat, lon)
        }
      group.add(new THREE.LineSegments(
        new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineBasicMaterial({ color: 0x0a3a6a, transparent: true, opacity: 0.35 }),
      ))
    }

    // ── Atmosphere shell ───────────────────────────────────────────────────
    group.add(new THREE.Mesh(
      new THREE.SphereGeometry(GLOBE_R * 1.04, 32, 32),
      new THREE.MeshBasicMaterial({ color: 0x001a33, transparent: true, opacity: 0.2, side: THREE.BackSide }),
    ))

    // ── Hub nodes ──────────────────────────────────────────────────────────
    const hubPos    = HUB_LL.map(([la, lo]) => ll2v(la, lo))
    const hubMeshes = [], hubCores = []
    const hubFlare  = new Float32Array(hubPos.length)

    hubPos.forEach(pos => {
      const outer = new THREE.Mesh(
        new THREE.SphereGeometry(5.5, 12, 12),
        new THREE.MeshBasicMaterial({ color: 0x00aaff, blending: THREE.AdditiveBlending, depthWrite: false }),
      )
      outer.position.copy(pos); group.add(outer); hubMeshes.push(outer)

      const core = new THREE.Mesh(
        new THREE.SphereGeometry(2.5, 8, 8),
        new THREE.MeshBasicMaterial({ color: 0xffffff, blending: THREE.AdditiveBlending, depthWrite: false }),
      )
      core.position.copy(pos); group.add(core); hubCores.push(core)
    })

    // ── Mid nodes ──────────────────────────────────────────────────────────
    const midPos = Array.from({ length: MID_COUNT }, () => ll2v(...randPopLL()))
    {
      const buf = new Float32Array(midPos.length * 3)
      midPos.forEach((v, i) => { buf[i*3]=v.x; buf[i*3+1]=v.y; buf[i*3+2]=v.z })
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(buf, 3))
      group.add(new THREE.Points(geo, new THREE.PointsMaterial({
        color: 0x00ccff, size: 3, sizeAttenuation: true,
        transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false,
      })))
    }

    // ── Edge nodes ─────────────────────────────────────────────────────────
    const edgePos = Array.from({ length: EDGE_COUNT }, () => ll2v(...randPopLL()))
    {
      const buf = new Float32Array(edgePos.length * 3)
      edgePos.forEach((v, i) => { buf[i*3]=v.x; buf[i*3+1]=v.y; buf[i*3+2]=v.z })
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(buf, 3))
      group.add(new THREE.Points(geo, new THREE.PointsMaterial({
        color: 0x0055aa, size: 1.5, sizeAttenuation: true,
        transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending, depthWrite: false,
      })))
    }

    // ── Connection arcs ────────────────────────────────────────────────────
    const hhPts = [], hhLongPts = []
    const hmPts = [], mmPts = [], mePts = [], eePts = []
    const allCurves = []

    const norm = v => v.clone().normalize()

    for (let i = 0; i < hubPos.length; i++) {
      for (let j = i + 1; j < hubPos.length; j++) {
        const dot  = norm(hubPos[i]).dot(norm(hubPos[j]))
        const lift = adaptLift(hubPos[i], hubPos[j], 40)
        const pts  = makeArcPts(hubPos[i], hubPos[j], lift)
        const cp   = hubPos[i].clone().add(hubPos[j]).normalize().multiplyScalar(GLOBE_R + lift)
        allCurves.push(new THREE.QuadraticBezierCurve3(hubPos[i].clone(), cp, hubPos[j].clone()))
        if (dot < -0.3) hhLongPts.push(pts)
        else hhPts.push(pts)
      }
    }

    for (let i = 0; i < hubPos.length; i++) {
      const ni = norm(hubPos[i])
      const sorted = midPos
        .map((m, j) => [ni.dot(norm(m)), j])
        .filter(([d]) => d > -0.5)
        .sort((a, b) => b[0] - a[0])
        .slice(0, 15)
      sorted.forEach(([, j]) => {
        const lift = adaptLift(hubPos[i], midPos[j], 22)
        hmPts.push(makeArcPts(hubPos[i], midPos[j], lift))
        const cp = hubPos[i].clone().add(midPos[j]).normalize().multiplyScalar(GLOBE_R + lift)
        allCurves.push(new THREE.QuadraticBezierCurve3(hubPos[i].clone(), cp, midPos[j].clone()))
      })
    }

    const mmDone = new Set()
    for (let i = 0; i < midPos.length; i++) {
      const ni = norm(midPos[i])
      midPos
        .map((m, j) => [ni.dot(norm(m)), j])
        .filter(([d, j]) => j !== i && d > 0.5)
        .sort((a, b) => b[0] - a[0])
        .slice(0, 6)
        .forEach(([, j]) => {
          const key = Math.min(i,j) * 10000 + Math.max(i,j)
          if (mmDone.has(key)) return
          mmDone.add(key)
          mmPts.push(makeArcPts(midPos[i], midPos[j], 14, 16))
          const cp = midPos[i].clone().add(midPos[j]).normalize().multiplyScalar(GLOBE_R + 14)
          allCurves.push(new THREE.QuadraticBezierCurve3(midPos[i].clone(), cp, midPos[j].clone()))
        })
    }

    for (let i = 0; i < midPos.length; i++) {
      const ni = norm(midPos[i])
      edgePos
        .map((e, j) => [ni.dot(norm(e)), j])
        .sort((a, b) => b[0] - a[0])
        .slice(0, 3)
        .forEach(([, j]) => mePts.push(makeArcPts(midPos[i], edgePos[j], 8, 10)))
    }

    const eeDone = new Set()
    for (let i = 0; i < edgePos.length; i++) {
      const ni = norm(edgePos[i])
      edgePos
        .map((e, j) => [ni.dot(norm(e)), j])
        .filter(([, j]) => j !== i)
        .sort((a, b) => b[0] - a[0])
        .slice(0, 2)
        .forEach(([, j]) => {
          const key = Math.min(i,j) * 100000 + Math.max(i,j)
          if (eeDone.has(key)) return
          eeDone.add(key)
          eePts.push(makeArcPts(edgePos[i], edgePos[j], 5, 8))
        })
    }

    buildLineSegs(group, hhPts,     0x00ccff, 0.80)
    buildLineSegs(group, hhLongPts, 0x00aaff, 0.25, false)
    buildLineSegs(group, hmPts,     0x0088cc, 0.50)
    buildLineSegs(group, mmPts,     0x006699, 0.32)
    buildLineSegs(group, mePts,     0x004488, 0.35)
    buildLineSegs(group, eePts,     0x003366, 0.22)

    // ── Energy travelers ───────────────────────────────────────────────────
    const tBuf = new Float32Array(MAX_TRAVELERS * 3).fill(9999)
    const tGeo = new THREE.BufferGeometry()
    tGeo.setAttribute('position', new THREE.BufferAttribute(tBuf, 3))
    group.add(new THREE.Points(tGeo, new THREE.PointsMaterial({
      color: 0x00ffff, size: 3.5, sizeAttenuation: true,
      transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false,
    })))

    const travelers = []
    const spawnT = () => {
      if (!allCurves.length) return
      travelers.push({ ci: (Math.random() * allCurves.length) | 0, t: 0, speed: 0.003 + Math.random() * 0.008, dir: 1 })
    }
    for (let i = 0; i < MAX_TRAVELERS; i++) spawnT()

    // ── Inertia drag ───────────────────────────────────────────────────────
    let isDragging = false
    let lastMouseX = 0, lastMouseY = 0
    let velocityX  = 0, velocityY  = 0

    const startDrag = (x, y) => { isDragging = true; lastMouseX = x; lastMouseY = y; velocityX = 0; velocityY = 0 }
    const moveDrag  = (x, y) => {
      if (!isDragging) return
      velocityX = (x - lastMouseX) * 0.01
      velocityY = (y - lastMouseY) * 0.01
      group.rotation.y += velocityX
      group.rotation.x = Math.max(-Math.PI/3, Math.min(Math.PI/3, group.rotation.x + velocityY))
      lastMouseX = x; lastMouseY = y
    }
    const endDrag = () => { isDragging = false }

    const onMouseDown  = e => startDrag(e.clientX, e.clientY)
    const onMouseMove  = e => moveDrag(e.clientX, e.clientY)
    const onMouseUp    = ()  => endDrag()
    const onMouseLeave = ()  => endDrag()
    const onTouchStart = e  => { e.preventDefault(); startDrag(e.touches[0].clientX, e.touches[0].clientY) }
    const onTouchMove  = e  => { if (isDragging) { e.preventDefault(); moveDrag(e.touches[0].clientX, e.touches[0].clientY) } }
    const onTouchEnd   = ()  => endDrag()

    let targetFov = camera.fov
    const onWheel = e => { targetFov = Math.max(30, Math.min(90, targetFov + e.deltaY * 0.04)) }

    canvas.addEventListener('mousedown',  onMouseDown)
    window.addEventListener('mousemove',  onMouseMove)
    window.addEventListener('mouseup',    onMouseUp)
    canvas.addEventListener('mouseleave', onMouseLeave)
    canvas.addEventListener('touchstart', onTouchStart, { passive: false })
    window.addEventListener('touchmove',  onTouchMove,  { passive: false })
    window.addEventListener('touchend',   onTouchEnd)
    canvas.addEventListener('wheel',      onWheel, { passive: true })

    // Click: flare nearest hub — use container-relative coords
    const raycaster = new THREE.Raycaster()
    const onClick = e => {
      if (Math.abs(velocityX) > 0.002 || Math.abs(velocityY) > 0.002) return
      const rect = el.getBoundingClientRect()
      const ndcX =  ((e.clientX - rect.left) / rect.width)  * 2 - 1
      const ndcY = -((e.clientY - rect.top)  / rect.height) * 2 + 1
      raycaster.setFromCamera({ x: ndcX, y: ndcY }, camera)
      let best = -1, bestD = Infinity
      hubMeshes.forEach((m, i) => {
        const wp = new THREE.Vector3(); m.getWorldPosition(wp)
        const d = raycaster.ray.distanceToPoint(wp)
        if (d < bestD) { bestD = d; best = i }
      })
      if (best >= 0 && bestD < 50) hubFlare[best] = 2.0
    }
    canvas.addEventListener('click', onClick)

    // ── Resize via ResizeObserver (fills container, not window) ────────────
    const onResize = () => {
      const w = el.clientWidth || 800, h = el.clientHeight || 600
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    const resizeObs = new ResizeObserver(onResize)
    resizeObs.observe(el)

    // ── Animation loop ─────────────────────────────────────────────────────
    let animId, elapsed = 0
    const clock = new THREE.Clock()
    const hhCount = hhPts.length + hhLongPts.length

    const animate = () => {
      animId = requestAnimationFrame(animate)
      const dt = clock.getDelta()
      elapsed += dt
      const sm = thinkRef.current ? 2.0 : speakRef.current ? 1.5 : 1.0

      if (Math.abs(camera.fov - targetFov) > 0.01) {
        camera.fov += (targetFov - camera.fov) * 0.12
        camera.updateProjectionMatrix()
      }

      if (!isDragging) {
        group.rotation.y += velocityX
        group.rotation.x = Math.max(-Math.PI/3, Math.min(Math.PI/3, group.rotation.x + velocityY))
        velocityX *= 0.95; velocityY *= 0.95
        if (Math.abs(velocityX) < 0.0001) velocityX = 0
        if (Math.abs(velocityY) < 0.0001) velocityY = 0
        if (velocityX === 0) group.rotation.y += BASE_SPEED * sm
      }

      hubMeshes.forEach((m, i) => {
        const pulse = 1 + 0.25 * Math.sin(elapsed * 1.6 + i * 0.85)
        const fl    = hubFlare[i]
        if (fl > 0) hubFlare[i] = Math.max(0, fl - 0.045)
        const scale = pulse * (1 + fl * 0.6)
        m.scale.setScalar(scale); hubCores[i].scale.setScalar(scale * 0.9)
        m.material.opacity = Math.min(1, 0.85 + fl * 0.4)
        hubCores[i].material.opacity = Math.min(1, 0.9 + fl * 0.4)
      })

      for (let i = 0; i < travelers.length; i++) {
        const tv = travelers[i]; const curv = allCurves[tv.ci]
        if (!curv) { tv.ci = (Math.random() * allCurves.length) | 0; continue }
        tv.t += tv.speed * tv.dir * sm
        if (tv.t >= 1 || tv.t <= 0) {
          if (tv.ci < hhCount + hmPts.length) {
            const ri = (Math.random() * hubPos.length) | 0
            hubFlare[ri] = Math.max(hubFlare[ri], 0.5)
          }
          tv.ci = (Math.random() * allCurves.length) | 0; tv.t = 0; tv.dir = 1
        }
        const pt = allCurves[tv.ci].getPoint(Math.max(0, Math.min(1, tv.t)))
        const idx = i * 3; tBuf[idx] = pt.x; tBuf[idx+1] = pt.y; tBuf[idx+2] = pt.z
      }
      while (travelers.length < MAX_TRAVELERS) spawnT()
      tGeo.attributes.position.needsUpdate = true

      renderer.render(scene, camera)
    }
    animate()

    return () => {
      cancelAnimationFrame(animId)
      resizeObs.disconnect()
      canvas.removeEventListener('mousedown',  onMouseDown)
      window.removeEventListener('mousemove',  onMouseMove)
      window.removeEventListener('mouseup',    onMouseUp)
      canvas.removeEventListener('mouseleave', onMouseLeave)
      canvas.removeEventListener('touchstart', onTouchStart)
      window.removeEventListener('touchmove',  onTouchMove)
      window.removeEventListener('touchend',   onTouchEnd)
      canvas.removeEventListener('wheel',      onWheel)
      canvas.removeEventListener('click',      onClick)
      renderer.dispose()
      if (el.contains(canvas)) el.removeChild(canvas)
    }
  }, [])

  return (
    <div ref={mountRef} style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
      <div style={{
        position: 'absolute', top: 14, left: 16, zIndex: 2, pointerEvents: 'none',
        fontFamily: 'Orbitron, monospace', fontSize: 8, fontWeight: 700,
        letterSpacing: '2.5px', color: 'rgba(0,170,255,0.4)',
        textTransform: 'uppercase',
      }}>Global Network — Tactical Overview</div>
      <div style={{
        position: 'absolute', top: 12, right: 16, zIndex: 2, pointerEvents: 'none',
        fontFamily: '"Share Tech Mono", monospace', fontSize: 10,
        color: '#00ff88', textShadow: '0 0 8px #00ff88',
      }}>● LIVE</div>
    </div>
  )
}
