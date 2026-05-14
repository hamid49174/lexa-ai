// Lexa 3D Voice Orb — Dot-grid sphere with vertex-colored hotspots
// Technique: dark metallic core + vertex-colored dots shell
// Hotspot colors: Violet #7c3aed, Fuchsia #d946ef, Amber #f59e0b
// Audio-reactive: asymmetric lerp smoothing, peak tracking, Siri-like deformation

class LexaOrb3D {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    if (!this.container) {
      console.warn(`Container #${containerId} not found for LexaOrb3D`);
      return;
    }

    this.options = Object.assign({
      baseScale: 3.5,
      detail: 24,
      wobbleSpeed: 0.0005,
      rotationSpeedY: 0.003,
      rotationSpeedX: 0.001,
      baseWobble: 0.015,
      audioImpactMultiplier: 0.7
    }, options);

    this.simplex = new SimplexNoise();
    this.originalVertices = [];
    this.coreOriginalVertices = [];
    this.volume = 0;
    this.smoothVolume = 0;
    this.peakVolume = 0;
    this.animationFrameId = null;
    this._lastBreathVal = 0;

    // Asymmetric lerp constants
    this.ATTACK = 0.25;
    this.RELEASE = 0.06;
    this.PEAK_DECAY = 0.03;

    // Hotspot definitions (positions will be set relative to R)
    this.hotspots = [
      { color: new THREE.Color(0x7c3aed), dir: new THREE.Vector3(-0.6, 0.65, 0.5).normalize() },   // Violet
      { color: new THREE.Color(0xd946ef), dir: new THREE.Vector3(0.5, 0.6, 0.55).normalize() },     // Fuchsia
      { color: new THREE.Color(0xf59e0b), dir: new THREE.Vector3(0.55, -0.5, 0.6).normalize() }     // Amber
    ];
    // Base dot color (dim purple)
    this.baseColor = new THREE.Color(0x2a1845);

    // Store base light values for audio modulation
    this._baseLights = {
      violet: { intensity: 10, distance: 7 },
      fuchsia: { intensity: 8, distance: 6 },
      amber: { intensity: 9, distance: 6 }
    };

    this.initScene();
    this.animate = this.animate.bind(this);
    this.start();
  }

  initScene() {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    const R = this.options.baseScale;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    this.camera.position.z = 12;

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.container.appendChild(this.renderer.domElement);

    // ── GROUP: everything rotates together ──
    this.group = new THREE.Group();
    this.scene.add(this.group);

    // ── LAYER 1: Dark metallic core — catches PointLight specular highlights ──
    const coreGeo = new THREE.SphereGeometry(R * 0.92, 96, 96);
    const corePos = coreGeo.attributes.position;
    for (let i = 0; i < corePos.count; i++) {
      this.coreOriginalVertices.push(new THREE.Vector3(
        corePos.getX(i), corePos.getY(i), corePos.getZ(i)
      ));
    }
    const coreMat = new THREE.MeshPhongMaterial({
      color: 0x0a0018,
      specular: 0xccaaff,
      shininess: 140,
      transparent: true,
      opacity: 0.95
    });
    this.core = new THREE.Mesh(coreGeo, coreMat);
    this.group.add(this.core);

    // ── LAYER 2: Dot-grid shell with vertex colors (Icosahedron = even distribution) ──
    const shellGeo = new THREE.IcosahedronGeometry(R, this.options.detail);
    const shellPos = shellGeo.attributes.position;
    const vertexCount = shellPos.count;

    // Store original vertices
    for (let i = 0; i < vertexCount; i++) {
      this.originalVertices.push(new THREE.Vector3(
        shellPos.getX(i), shellPos.getY(i), shellPos.getZ(i)
      ));
    }

    // Create vertex colors buffer
    const colors = new Float32Array(vertexCount * 3);
    shellGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    // Initial color computation
    this._computeVertexColors(colors, 0, 0);

    const dotsMat = new THREE.PointsMaterial({
      size: 0.055,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.9,
      vertexColors: true
    });
    this.dots = new THREE.Points(shellGeo, dotsMat);
    this.group.add(this.dots);

    // ── PointLights still needed for core specular highlights ──
    this.lightViolet = new THREE.PointLight(0x7c3aed, 10, 7, 2);
    this.lightViolet.position.set(-R * 0.6, R * 0.65, R * 0.5);
    this.group.add(this.lightViolet);

    this.lightFuchsia = new THREE.PointLight(0xd946ef, 8, 6, 2);
    this.lightFuchsia.position.set(R * 0.5, R * 0.6, R * 0.55);
    this.group.add(this.lightFuchsia);

    this.lightAmber = new THREE.PointLight(0xf59e0b, 9, 6, 2);
    this.lightAmber.position.set(R * 0.55, -R * 0.5, R * 0.6);
    this.group.add(this.lightAmber);

    // Dim ambient
    this.scene.add(new THREE.AmbientLight(0x1a0a30, 0.25));

    // Resize handler
    this.onResize = () => {
      if (!this.container) return;
      const w = this.container.clientWidth;
      const h = this.container.clientHeight;
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(w, h);
    };
    window.addEventListener("resize", this.onResize);
  }

  // Compute vertex colors based on proximity to hotspot directions
  // vol parameter controls hotspot expansion and brightness
  _computeVertexColors(colors, time, vol) {
    const tmpColor = new THREE.Color();
    const vertDir = new THREE.Vector3();
    // Hotspot radius expands with volume: threshold drops from 0.3 to 0.1
    const hotspotThreshold = 0.3 - vol * 0.2;
    // Brightness boost with volume
    const brightBoost = 1.0 + vol * 0.6;

    for (let i = 0; i < this.originalVertices.length; i++) {
      const v = this.originalVertices[i];
      vertDir.copy(v).normalize();

      // Start with base color
      tmpColor.copy(this.baseColor);

      // Blend in each hotspot based on angular proximity
      for (const hs of this.hotspots) {
        // dot product = cosine of angle between vertex direction and hotspot direction
        const dot = vertDir.dot(hs.dir);
        // Influence: strong falloff — only close vertices get colored
        const influence = Math.max(0, (dot - hotspotThreshold) / (1.0 - hotspotThreshold));
        const strength = Math.pow(influence, 2.5) * 0.9; // Sharp falloff, max 90% blend

        if (strength > 0.01) {
          tmpColor.lerp(hs.color, strength);
        }
      }

      // Add subtle brightness variation based on noise for shimmer
      const shimmer = 0.85 + 0.15 * Math.sin(time * 2 + v.x * 3 + v.y * 5);
      tmpColor.multiplyScalar(shimmer * brightBoost);

      colors[i * 3] = Math.min(tmpColor.r, 1.0);
      colors[i * 3 + 1] = Math.min(tmpColor.g, 1.0);
      colors[i * 3 + 2] = Math.min(tmpColor.b, 1.0);
    }
  }

  setVolume(vol) {
    this.volume = vol;
  }

  // ── Conversation state visual modes (ChatGPT Voice style) ──
  setConversationState(state) {
    this._convState = state;
  }

  animate() {
    this.animationFrameId = requestAnimationFrame(this.animate);
    if (!this.dots || !this.core) return;

    const vol = this.volume;
    const convState = this._convState || null;

    // ── State-based animation parameters ──
    // listening: calm breathing + volume reactive
    // processing: faster rotation, pulsing glow, no volume
    // speaking: smooth scale pulse, bright, medium rotation
    let stateRotBoost = 1.0;
    let stateBrightBoost = 0;
    let stateScaleBase = 1.0;
    let stateWobbleExtra = 0;

    if (convState === "processing") {
      // Thinking mode: faster rotation, gentle pulse
      stateRotBoost = 3.0;
      stateBrightBoost = 0.3 + Math.sin(performance.now() * 0.006) * 0.15;
      stateScaleBase = 1.0 + Math.sin(performance.now() * 0.004) * 0.03;
      stateWobbleExtra = 0.08;
    } else if (convState === "speaking") {
      // Speaking mode: smooth, bright, medium activity
      stateRotBoost = 1.5;
      stateBrightBoost = 0.4;
      stateScaleBase = 1.05;
      stateWobbleExtra = 0.04;
    } else if (convState === "listening") {
      // Listening mode: calm, receptive, volume-reactive
      stateRotBoost = 0.8;
      stateBrightBoost = 0.1;
      stateScaleBase = 1.0;
    }

    // ── Asymmetric smoothing: fast attack, slow release ──
    if (vol > this.smoothVolume) {
      this.smoothVolume += (vol - this.smoothVolume) * this.ATTACK;
    } else {
      this.smoothVolume += (vol - this.smoothVolume) * this.RELEASE;
    }
    if (this.smoothVolume < 0.001) this.smoothVolume = 0;

    // ── Peak tracking for flash effects ──
    if (vol > this.peakVolume) {
      this.peakVolume = vol;
    } else {
      this.peakVolume *= (1.0 - this.PEAK_DECAY);
    }
    if (this.peakVolume < 0.001) this.peakVolume = 0;

    const sv = this.smoothVolume;
    // Effective visual intensity: combine volume + state boost
    const ev = Math.min(1.0, sv + stateBrightBoost);

    // ── Audio-reactive rotation speed boost ──
    const rotMul = stateRotBoost * (1.0 + sv * 2.0);
    this.group.rotation.y += this.options.rotationSpeedY * rotMul;
    this.group.rotation.x += this.options.rotationSpeedX * rotMul;

    // ── Scale pulse: state base + volume ──
    const scalePulse = stateScaleBase + sv * 0.15;
    this.group.scale.setScalar(scalePulse);

    const time = performance.now() * this.options.wobbleSpeed;
    const wobbleStrength = this.options.baseWobble + stateWobbleExtra + sv * this.options.audioImpactMultiplier;

    // ── Breathing value for idle detection ──
    const breathVal = Math.sin(time * 2) * 0.5;
    const breathChanged = Math.abs(breathVal - this._lastBreathVal) > 0.001;
    this._lastBreathVal = breathVal;

    // ── Performance: skip geometry updates when idle and no breathing change ──
    const needsGeometryUpdate = ev >= 0.005 || breathChanged || convState === "processing";

    if (needsGeometryUpdate) {
      // Deform dot shell
      const dotPos = this.dots.geometry.attributes.position;
      for (let i = 0; i < dotPos.count; i++) {
        const v = this.originalVertices[i];
        const noise = this.simplex.noise3D(
          v.x * 0.6 + time, v.y * 0.6 + time, v.z * 0.6
        );
        const d = 1 + (noise * 0.15 * wobbleStrength);
        dotPos.setXYZ(i, v.x * d, v.y * d, v.z * d);
      }
      dotPos.needsUpdate = true;

      // Deform core (slightly less)
      const corePos = this.core.geometry.attributes.position;
      for (let i = 0; i < corePos.count; i++) {
        const v = this.coreOriginalVertices[i];
        const noise = this.simplex.noise3D(
          v.x * 0.6 + time, v.y * 0.6 + time, v.z * 0.6
        );
        const d = 1 + (noise * 0.13 * wobbleStrength);
        corePos.setXYZ(i, v.x * d, v.y * d, v.z * d);
      }
      corePos.needsUpdate = true;
    }

    // ── Audio-reactive vertex colors: hotspots expand and brighten ──
    const colorAttr = this.dots.geometry.attributes.color;
    this._computeVertexColors(colorAttr.array, time, ev);
    colorAttr.needsUpdate = true;

    // ── Audio-reactive dot size ──
    this.dots.material.size = 0.055 + ev * 0.03;

    // ── Audio-reactive core specular boost ──
    this.core.material.shininess = 140 + ev * 100;

    // ── Audio-reactive lights: intensity and range boost ──
    const breathe = Math.sin(performance.now() * 0.001) * 0.2 + 1;
    const intensityMul = breathe * (1.0 + ev * 2.0);
    const rangeMul = 1.0 + ev * 1.0;

    this.lightViolet.intensity = this._baseLights.violet.intensity * intensityMul;
    this.lightViolet.distance = this._baseLights.violet.distance * rangeMul;

    this.lightFuchsia.intensity = this._baseLights.fuchsia.intensity * intensityMul;
    this.lightFuchsia.distance = this._baseLights.fuchsia.distance * rangeMul;

    this.lightAmber.intensity = this._baseLights.amber.intensity * intensityMul;
    this.lightAmber.distance = this._baseLights.amber.distance * rangeMul;

    this.renderer.render(this.scene, this.camera);
  }

  start() {
    if (!this.animationFrameId) this.animate();
  }

  stop() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
  }

  destroy() {
    this.stop();
    window.removeEventListener("resize", this.onResize);
    if (this.container && this.renderer) {
      this.container.removeChild(this.renderer.domElement);
    }
  }
}
