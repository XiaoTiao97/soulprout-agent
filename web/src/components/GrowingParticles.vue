<template>
  <canvas
    ref="canvasRef"
    style="position: absolute; inset: 0; width: 100%; height: 100%; z-index: 1; pointer-events: auto;"
  ></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const canvasRef = ref(null)

let cleanupFn = null

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  let w = 0, h = 0, animId = 0, running = true, time = 0
  let initialized = false

  const MAX = 60
  const seeds = []
  const mouse = { x: -1000, y: -1000 }

  const createSeed = () => {
    const x = Math.random() * w
    return {
      x, y: h + 10 + Math.random() * 30,
      originX: x,
      size: 0,
      speedY: 0.25 + Math.random() * 0.45,
      phase: Math.random() * Math.PI * 2,
      amp: 25 + Math.random() * 50,
      alpha: 0,
      life: 0,
      maxLife: 350 + Math.random() * 250,
      pulsePhase: Math.random() * Math.PI * 2,
      glowSize: 3 + Math.random() * 5,
    }
  }

  const init = () => {
    seeds.length = 0
    for (let i = 0; i < MAX; i++) {
      const s = createSeed()
      s.y = Math.random() * h * 1.1
      s.life = Math.random() * s.maxLife
      seeds.push(s)
    }
  }

  const resize = () => {
    const parent = canvas.parentElement
    if (!parent) return
    const newW = parent.offsetWidth
    const newH = parent.offsetHeight
    if (newW === 0 || newH === 0) return

    const wasUninitialized = !initialized
    w = newW
    h = newH
    const dpr = Math.min(window.devicePixelRatio, 2)
    canvas.width = w * dpr
    canvas.height = h * dpr
    canvas.style.width = w + 'px'
    canvas.style.height = h + 'px'
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    if (wasUninitialized) {
      initialized = true
      init()
    }
  }

  const onMove = (e) => {
    const rect = canvas.getBoundingClientRect()
    mouse.x = e.clientX - rect.left
    mouse.y = e.clientY - rect.top
  }
  const onLeave = () => { mouse.x = -1000 }

  canvas.addEventListener('mousemove', onMove)
  canvas.addEventListener('mouseleave', onLeave)

  const draw = () => {
    if (!running) return
    animId = requestAnimationFrame(draw)
    if (!initialized) return
    time += 0.006
    ctx.clearRect(0, 0, w, h)

    for (const s of seeds) {
      s.life++
      if (s.life > s.maxLife || s.y < -30) {
        Object.assign(s, createSeed())
        continue
      }

      s.y -= s.speedY
      const lr = s.life / s.maxLife
      s.x = s.originX + Math.sin(time * 1.8 + s.phase) * s.amp * (0.3 + lr * 0.7)

      if (lr < 0.08) s.size = (lr / 0.08) * 2.8
      else if (lr < 0.5) s.size = 2.8
      else s.size = 2.8 * ((1 - lr) / 0.5)

      if (lr < 0.06) s.alpha = (lr / 0.06) * 0.3
      else if (lr > 0.85) s.alpha = 0.3 * ((1 - lr) / 0.15)
      else s.alpha = 0.3

      s.alpha += Math.sin(time * 3 + s.pulsePhase) * 0.04
      s.alpha = Math.max(0, Math.min(0.38, s.alpha))

      const mdx = s.x - mouse.x, mdy = s.y - mouse.y
      const md = Math.sqrt(mdx * mdx + mdy * mdy)
      if (md < 160) {
        const f = (1 - md / 160) * 2.5
        s.x += (mdx / md) * f
        s.y += (mdy / md) * f * 0.4
      }
    }

    for (const s of seeds) {
      if (s.alpha <= 0) continue

      const grad = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.glowSize)
      grad.addColorStop(0, `rgba(30, 180, 140, ${s.alpha * 0.08})`)
      grad.addColorStop(1, 'rgba(30, 180, 140, 0)')
      ctx.beginPath()
      ctx.arc(s.x, s.y, s.glowSize, 0, Math.PI * 2)
      ctx.fillStyle = grad
      ctx.fill()

      ctx.beginPath()
      ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(30, 180, 140, ${s.alpha})`
      ctx.fill()
    }
  }

  // ResizeObserver detects when the canvas goes from hidden (size=0) to visible
  const ro = new ResizeObserver(() => { resize() })
  ro.observe(canvas.parentElement || canvas)

  resize()
  draw()

  cleanupFn = () => {
    running = false
    cancelAnimationFrame(animId)
    ro.disconnect()
    canvas.removeEventListener('mousemove', onMove)
    canvas.removeEventListener('mouseleave', onLeave)
  }
})

onUnmounted(() => {
  if (cleanupFn) cleanupFn()
})
</script>
