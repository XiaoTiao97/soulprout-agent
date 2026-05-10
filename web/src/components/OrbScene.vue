<template>
  <div class="orb-container" ref="containerRef">
    <div class="orb-canvas-container"></div>
    <div class="vignette"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import * as THREE from 'three'
import { EffectComposer, RenderPass, EffectPass, BloomEffect, KernelSize } from 'postprocessing'

const COLORS = [
  '#1eb48c', '#1aaa84', '#169c7a',
  '#e8e8e8', '#f0f0f0',
  '#1eb48c', '#1aaa84',
]

const SPHERE_POSITIONS = [
  [2.18, -1.38, 0], [-2.28, -1.21, 0], [2.28, 1.21, 0],
  [-2.18, 1.38, 0], [0, 2, 0], [0, -2, 0],
]
const SPHERE_COLOR_INDICES = [0, 1, 2, 0, 1, 2]

const containerRef = ref(null)
let cleanupFn = null

onMounted(() => {
  const container = containerRef.value
  if (!container) return

  const canvasContainer = container.querySelector('.orb-canvas-container')

  const scene = new THREE.Scene()
  scene.background = new THREE.Color('#ffffff')

  const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100)
  camera.position.set(0, 0, 6)

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
  renderer.setSize(window.innerWidth, window.innerHeight)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.domElement.style.width = '100%'
  renderer.domElement.style.height = '100%'
  renderer.domElement.style.display = 'block'
  canvasContainer.appendChild(renderer.domElement)

  const uniforms = {
    uTime: { value: 0 },
    uGlowIntensity: { value: 0.55 },
    uColorA: { value: new THREE.Color(COLORS[0]) },
    uColorB: { value: new THREE.Color(COLORS[1]) },
    uColorC: { value: new THREE.Color(COLORS[2]) },
    uMouse: { value: new THREE.Vector2(0.5, 0.5) },
    uResolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
  }

  const sphereVertexShader = `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `
  const sphereFragmentShader = `
    uniform float uTime;
    uniform vec3 uColor;
    uniform float uGlowIntensity;
    varying vec2 vUv;
    void main() {
      vec2 uv = vUv;
      vec2 center = uv * 2.0 - 1.0;
      float noise = fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453);
      float dist = length(center);
      float glow = pow(0.7 - dist, 2.0);
      float pulsation = sin(uTime * 2.0) * 0.1 + 1.0;
      glow *= pulsation * uGlowIntensity * 0.5 * (1.0 + noise * 0.2);
      gl_FragColor = vec4(uColor, glow);
    }
  `

  const haloVertexShader = `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `
  const haloFragmentShader = `
    uniform float uTime;
    uniform vec3 uColorA;
    uniform vec3 uColorB;
    uniform vec3 uColorC;
    uniform vec2 uMouse;
    uniform float uGlowIntensity;
    varying vec2 vUv;
    void main() {
      vec2 center = vUv - vec2(0.5);
      float dist = length(center);
      vec2 mouseOffset = (uMouse - 0.5) * 0.1;
      float mouseDist = length(center - mouseOffset);
      float breath = sin(uTime * 0.5) * 0.05 + 0.95;
      float halo = smoothstep(0.5, 0.1, mouseDist) * 0.3 * uGlowIntensity * breath;
      float ambient = smoothstep(0.8, 0.2, dist) * 0.08 * uGlowIntensity * breath;
      vec3 color = mix(mix(uColorA, uColorB, vUv.x), uColorC, vUv.y);
      gl_FragColor = vec4(color, halo + ambient);
    }
  `

  // Spheres
  const sphereGeo = new THREE.SphereGeometry(1, 64, 64)
  const spheres = []

  SPHERE_POSITIONS.forEach((pos, index) => {
    const mat = new THREE.ShaderMaterial({
      vertexShader: sphereVertexShader,
      fragmentShader: sphereFragmentShader,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      uniforms: {
        uTime: uniforms.uTime,
        uColor: { value: new THREE.Color(COLORS[SPHERE_COLOR_INDICES[index]]) },
        uGlowIntensity: uniforms.uGlowIntensity,
      },
    })
    const mesh = new THREE.Mesh(sphereGeo, mat)
    mesh.position.set(pos[0], pos[1], pos[2])
    mesh.userData.initialPos = new THREE.Vector3(pos[0], pos[1], pos[2])
    scene.add(mesh)
    spheres.push(mesh)
  })

  // Halo
  const haloGeo = new THREE.CircleGeometry(4.5, 128)
  const haloMat = new THREE.ShaderMaterial({
    vertexShader: haloVertexShader,
    fragmentShader: haloFragmentShader,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    uniforms: {
      uTime: uniforms.uTime,
      uColorA: uniforms.uColorA,
      uColorB: uniforms.uColorB,
      uColorC: uniforms.uColorC,
      uMouse: uniforms.uMouse,
      uGlowIntensity: uniforms.uGlowIntensity,
    },
  })
  const halo = new THREE.Mesh(haloGeo, haloMat)
  halo.rotation.x = -Math.PI / 2
  scene.add(halo)

  // Post-processing
  const composer = new EffectComposer(renderer)
  composer.addPass(new RenderPass(scene, camera))
  const bloomEffect = new BloomEffect({
    resolutionScale: 0.5,
    kernelSize: KernelSize.LARGE,
    luminanceThreshold: 0.3,
  })
  composer.addPass(new EffectPass(camera, bloomEffect))

  const clock = new THREE.Clock()
  let running = true

  const animate = () => {
    if (!running) return
    requestAnimationFrame(animate)
    uniforms.uTime.value = clock.getElapsedTime()
    const time = uniforms.uTime.value

    camera.position.set(0, 0, 6)
    camera.lookAt(0, 0, 0)

    spheres.forEach((mesh, index) => {
      mesh.position.x = mesh.userData.initialPos.x + Math.sin(time * 0.5 + index) * 0.4
      mesh.position.y = mesh.userData.initialPos.y + Math.cos(time * 0.3 + index) * 0.3
      mesh.scale.setScalar(1.5 + Math.sin(time * 2 + index) * 0.2)
    })

    composer.render()
  }
  animate()

  const onResize = () => {
    camera.aspect = window.innerWidth / window.innerHeight
    camera.updateProjectionMatrix()
    renderer.setSize(window.innerWidth, window.innerHeight)
    composer.setSize(window.innerWidth, window.innerHeight)
    uniforms.uResolution.value.set(window.innerWidth, window.innerHeight)
  }
  window.addEventListener('resize', onResize)

  cleanupFn = () => {
    running = false
    window.removeEventListener('resize', onResize)
    renderer.dispose()
    composer.dispose()
    sphereGeo.dispose()
    haloGeo.dispose()
    spheres.forEach(s => s.material.dispose())
    haloMat.dispose()
    if (canvasContainer.contains(renderer.domElement)) {
      canvasContainer.removeChild(renderer.domElement)
    }
  }
})

onUnmounted(() => {
  if (cleanupFn) cleanupFn()
})
</script>

<style scoped>
.orb-container {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
}
.orb-canvas-container {
  position: absolute;
  inset: 0;
}
.orb-canvas-container canvas {
  display: block;
  width: 100% !important;
  height: 100% !important;
}
.vignette {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at center, transparent 40%, rgba(255, 255, 255, 0.3) 100%);
  pointer-events: none;
  z-index: 1;
}
</style>
