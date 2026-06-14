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
      wobbleSpeed: 0.0005,
      baseWobble: 0.02,
      audioImpactMultiplier: 0.7,
      maxPixelRatio: 1.5,
      geometryUpdateMs: 0,
      colorUpdateMs: 0
    }, options);

    this.simplex = new SimplexNoise();
    this.originalVertices = [];
    this.originalVertexDirs = [];
    this.coreOriginalVertices = [];
    this.volume = 0;
    this.smoothVolume = 0;
    this.peakVolume = 0;
    this.animationFrameId = null;
    this._lastBreathVal = 0;
    this._statePhase = Math.random() * Math.PI * 2;
    this._statePhaseB = Math.random() * Math.PI * 2;
    this._stateStartedAt = 0;
    this._motionSeed = Math.random() * 1000;
    this._lastFrameNow = 0;
    this._lastGeometryUpdate = 0;
    this._lastColorUpdate = 0;
    this._frameSpikeCount = 0;
    this._perfMode = 0;
    this._tmpColor = new THREE.Color();

    // Asymmetric lerp constants
    this.ATTACK = 0.25;
    this.RELEASE = 0.06;
    this.PEAK_DECAY = 0.03;

    // Hotspot definitions (positions will be set relative to R) using strictly the Fuchsia/Cyan/Violet palette
    this.hotspots = [
      { color: new THREE.Color(0x00f0ff), dir: new THREE.Vector3(-0.6, 0.65, 0.5).normalize() },   // Neon Cyan
      { color: new THREE.Color(0xff00a0), dir: new THREE.Vector3(0.5, 0.6, 0.55).normalize() },     // Vibrant Fuchsia
      { color: new THREE.Color(0x8a2be2), dir: new THREE.Vector3(0.55, -0.5, 0.6).normalize() }     // Deep Violet
    ];
    // Base dot color: dark glowing indigo-violet that blends elegantly with the obsidian core.
    this.baseColor = new THREE.Color(0x2a144a);

    // Store base light values for audio modulation
    this._baseLights = {
      violet: { intensity: 12, distance: 8 },
      fuchsia: { intensity: 10, distance: 7 },
      amber: { intensity: 10, distance: 7 }
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
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.options.maxPixelRatio));
    this.container.appendChild(this.renderer.domElement);

    // ── GROUP: everything rotates together ──
    this.group = new THREE.Group();
    this.scene.add(this.group);

    // ── LAYER 1: Dark metallic core — catches PointLight specular highlights ──
    const coreGeo = new THREE.SphereGeometry(R * 0.92, 32, 32);
    const corePos = coreGeo.attributes.position;
    for (let i = 0; i < corePos.count; i++) {
      this.coreOriginalVertices.push(new THREE.Vector3(
        corePos.getX(i), corePos.getY(i), corePos.getZ(i)
      ));
    }
    const coreMat = new THREE.MeshPhongMaterial({
      color: 0x05010a,       // Very dark pitch-black liquid obsidian core
      specular: 0x3a2266,    // Elegant, subtle dark violet highlights
      shininess: 150,        // High-end glossy reflection sheen
      transparent: true,
      opacity: 0.95
    });
    this.core = new THREE.Mesh(coreGeo, coreMat);
    this.core.visible = false; // Hide the old solid metallic core completely for hollow stardust look
    this.group.add(this.core);

    // ── LAYER 1B: Volumetric Holographic Glass Shell — adds premium depth, fresnel-like sheen ──
    const glassGeo = new THREE.SphereGeometry(R * 0.96, 32, 32);
    const glassMat = new THREE.MeshPhongMaterial({
      color: 0x0a0114,       // Deep dark glowing indigo glass
      emissive: 0x06000c,    // Extremely deep dark ambient glow
      specular: 0xffffff,    // Bright glistening glass specular reflection
      shininess: 160,
      transparent: true,
      opacity: 0.22,
      blending: THREE.AdditiveBlending
    });
    this.glassShell = new THREE.Mesh(glassGeo, glassMat);
    this.glassShell.visible = false; // Hide the glass shell completely for a beautiful hollow particle sphere
    this.group.add(this.glassShell);

    // ── LAYER 2: Dot-grid shell with custom organic random distribution matching serioushomebrew/js-3d-particlesphere ──
    const shellGeo = new THREE.BufferGeometry();
    const vertices = [];
    const numPoints = 1800; // Dense and beautiful stardust cloud
    const RADIAN = Math.PI / 180;

    for (let i = 0; i < numPoints; i++) {
      // Exact mathematical distribution from serioushomebrew/js-3d-particlesphere
      const t1 = 360 * Math.random() * RADIAN;
      const t2 = (180 * Math.random() - 90) * RADIAN;
      // Add subtle volumetric thickness variation for high-end stardust volumetric depth
      const pR = R * (0.96 + Math.random() * 0.08);
      const xx = pR * Math.cos(t2) * Math.sin(t1);
      const yy = pR * Math.sin(t2);
      const zz = pR * Math.cos(t2) * Math.cos(t1);
      vertices.push(xx, yy, zz);
    }
    shellGeo.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    const shellPos = shellGeo.attributes.position;
    const vertexCount = shellPos.count;

    // Store original vertices and initialize vibrant particle base colors matching the user's screenshot
    this.vertexBaseColors = [];
    for (let i = 0; i < vertexCount; i++) {
      const vertex = new THREE.Vector3(
        shellPos.getX(i), shellPos.getY(i), shellPos.getZ(i)
      );
      this.originalVertices.push(vertex);
      this.originalVertexDirs.push(vertex.clone().normalize());

      const rand = Math.random();
      let color;
      if (rand < 0.38) {
        color = new THREE.Color(0x00f0ff); // Neon Cyan / Blue
      } else if (rand < 0.73) {
        color = new THREE.Color(0xff00a0); // Vibrant Fuchsia / Pink
      } else {
        color = new THREE.Color(0x8a2be2); // Deep Blue Violet
      }
      this.vertexBaseColors.push(color);
    }

    // Create vertex colors buffer
    const colors = new Float32Array(vertexCount * 3);
    shellGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    // Initial color computation
    this._computeVertexColors(colors, 0, 0);

    const dotsMat = new THREE.PointsMaterial({
      size: 0.08,             // Perfectly proportioned tiny sharp pixels
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.95,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
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

    // Dim ambient: keep the Orb dark and volumetric instead of glossy/white.
    this.scene.add(new THREE.AmbientLight(0x2a0a45, 0.42));

    // Resize handler
    this.onResize = () => {
      if (!this.container) return;
      const w = this.container.clientWidth || 1;
      const h = this.container.clientHeight || 1;
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();

      const dpr = Math.min(window.devicePixelRatio || 1, this.options.maxPixelRatio);
      if (this.renderer.getPixelRatio() !== dpr) {
        this.renderer.setPixelRatio(dpr);
      }
      this.renderer.setSize(w, h);
    };
    window.addEventListener("resize", this.onResize);

    // Watch container size changes (compact class toggle, CSS transitions, layout flex)
    if (typeof ResizeObserver !== "undefined") {
      this.resizeObserver = new ResizeObserver(() => {
        this.onResize();
      });
      this.resizeObserver.observe(this.container);
    }
  }

  // Compute vertex colors based on proximity to hotspot directions
  // vol parameter controls hotspot expansion and brightness
  _computeVertexColors(colors, time, vol, phase = 0) {
    const tmpColor = this._tmpColor;
    // Hotspot radius expands with volume: threshold drops from 0.3 to 0.1
    const hotspotThreshold = 0.3 - vol * 0.2;
    // Brightness boost with volume
    const brightBoost = 1.0 + vol * 0.6;

    for (let i = 0; i < this.originalVertices.length; i++) {
      const v = this.originalVertices[i];
      const vertDir = this.originalVertexDirs[i];

      // Start with beautiful, pre-calculated random base color matching the user's reference image
      tmpColor.copy(this.vertexBaseColors[i] || this.baseColor);

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

      // Non-uniform shimmer: layered phases avoid a visible looping-video cadence.
      const shimmer = 0.84
        + 0.10 * Math.sin(time * 1.7 + v.x * 2.7 + v.y * 4.1 + phase)
        + 0.07 * Math.sin(time * 0.83 + v.z * 5.3 + v.x * 1.5 + phase * 0.37);
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
    if (this._convState !== state) {
      this._statePhase = Math.random() * Math.PI * 2;
      this._statePhaseB = Math.random() * Math.PI * 2;
      this._stateStartedAt = typeof performance !== "undefined" ? performance.now() : 0;
      this._motionSeed += 11.7 + Math.random() * 9.3;
    }
    this._convState = state;
  }

  _organicPulse(now, speed = 1, offset = 0) {
    const t = now * 0.001 * speed;
    const a = this._statePhase + offset;
    const b = this._statePhaseB + offset * 0.7;
    const value = 0.5
      + Math.sin(t * 1.37 + a) * 0.24
      + Math.sin(t * 0.71 + b) * 0.16
      + Math.sin(t * 2.13 + a * 0.43) * 0.08;
    return Math.max(0, Math.min(1, value));
  }

  _organicDrift(now, speed = 1, channel = 0) {
    const t = now * 0.00011 * speed;
    const seed = this._motionSeed + channel * 19.37;
    return (
      this.simplex.noise3D(seed, t, this._statePhase * 0.11) * 0.68
      + Math.sin(now * 0.00023 * speed + this._statePhase + channel) * 0.22
      + Math.sin(now * 0.00041 * speed + this._statePhaseB + channel * 0.7) * 0.10
    );
  }

  _applyOrganicOrientation(now, convState, sv, stateRotBoost) {
    const stateSpeed = convState === "processing"
      ? 1.35
      : convState === "speaking"
        ? 1.12
        : convState === "listening"
          ? 0.86
          : 0.46;
    const energy = Math.min(1.35, 0.72 + sv * 0.48 + stateRotBoost * 0.13);

    // Continuous base rotation like a real particle globe (restores js-3d-particlesphere function)
    this._baseRotY = (this._baseRotY || 0) + 0.0012 * stateSpeed * energy;
    this._baseRotX = (this._baseRotX || 0) + 0.0006 * stateSpeed * energy;

    const listenLean = convState === "listening" ? 0.045 : 0;
    const targetX = this._baseRotX + this._organicDrift(now, stateSpeed, 1) * 0.115 * energy - listenLean * 0.5;
    const targetY = this._baseRotY + this._organicDrift(now, stateSpeed, 2) * 0.165 * energy + listenLean;
    const targetZ = this._organicDrift(now, stateSpeed, 3) * 0.052 * energy;
    const ease = convState === "processing" ? 0.042 : 0.028;

    this.group.rotation.x += (targetX - this.group.rotation.x) * ease;
    this.group.rotation.y += (targetY - this.group.rotation.y) * ease;
    this.group.rotation.z += (targetZ - this.group.rotation.z) * ease;
  }

  animate() {
    this.animationFrameId = requestAnimationFrame(this.animate);
    // Avoid costly 3D rendering while the app is hidden.
    if (document.hidden) return;
    if (!this.dots || !this.core) return;

    // Skip the expensive geometry/color/render work while the orb is not visible
    // (e.g. the chat view is hidden because another view is active). The rAF loop
    // keeps running so the orb resumes automatically when the chat view returns.
    const canvas = this.renderer && this.renderer.domElement;
    if (canvas && canvas.offsetParent === null) {
      // Reset the frame timer so the first visible frame is not counted as a
      // spike (which would wrongly downgrade the performance mode).
      this._lastFrameNow = 0;
      return;
    }

    const now = performance.now();
    const frameDelta = this._lastFrameNow ? now - this._lastFrameNow : 16;
    this._lastFrameNow = now;
    if (frameDelta > 115) {
      this._frameSpikeCount += 1;
      if (this._frameSpikeCount >= 2) this._perfMode = Math.min(2, this._perfMode + 1);
    } else if (this._frameSpikeCount > 0 && frameDelta < 34) {
      this._frameSpikeCount -= 1;
    }
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
    let stateSyntheticVolume = 0;
    let stateShapeWarp = 0;

    if (convState === "processing") {
      // Thinking mode: faster rotation, gentle pulse
      stateRotBoost = 3.0;
      stateBrightBoost = 0.3 + Math.sin(now * 0.006) * 0.15;
      stateScaleBase = 1.0 + Math.sin(now * 0.004) * 0.03;
      stateWobbleExtra = 0.08;
    } else if (convState === "speaking") {
      // Speaking mode uses a synthetic cadence because TTS audio is played by HTMLAudio.
      const speechPulse = this._organicPulse(now, 1.45, 0.2);
      const speechFlutter = this._organicPulse(now, 2.1, 1.4);
      stateRotBoost = 2.25;
      stateBrightBoost = 0.34 + speechPulse * 0.18;
      stateScaleBase = 1.08 + speechPulse * 0.045;
      stateWobbleExtra = 0.10 + speechFlutter * 0.05;
      stateSyntheticVolume = 0.18 + speechPulse * 0.16;
    } else if (convState === "listening") {
      // Listening mode: the orb leans into the user with a slow breathing shape change.
      const listenPulse = this._organicPulse(now, 0.92, 0.6);
      const listenRipple = this._organicPulse(now, 1.35, 1.7);
      stateRotBoost = 1.35;
      stateBrightBoost = 0.22 + listenPulse * 0.16;
      stateScaleBase = 1.045 + listenPulse * 0.045;
      stateWobbleExtra = 0.18 + listenRipple * 0.08;
      stateSyntheticVolume = 0.08 + listenPulse * 0.12;
      stateShapeWarp = 0.07 + listenPulse * 0.06;
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

    const sv = Math.max(this.smoothVolume, stateSyntheticVolume);
    // Effective visual intensity: combine volume + state boost
    const ev = Math.min(1.0, sv + stateBrightBoost);

    // Organic orientation drift instead of constant spin. Constant spin made the
    // orb read like a short looping video.
    this._applyOrganicOrientation(now, convState, sv, stateRotBoost);

    // ── Scale pulse: state base + volume (Boosted heavily for point cloud impact) ──
    const scalePulse = stateScaleBase + sv * 0.45;
    this.group.scale.setScalar(scalePulse);

    const time = now * this.options.wobbleSpeed;
    const baseWobbleBreath = this.options.baseWobble + 0.005 * Math.sin(now * 0.0016);
    const wobbleStrength = baseWobbleBreath + stateWobbleExtra + sv * this.options.audioImpactMultiplier;

    // ── Breathing value for idle detection ──
    const breathVal = Math.sin(time * 2) * 0.5;
    const breathChanged = Math.abs(breathVal - this._lastBreathVal) > 0.001;
    this._lastBreathVal = breathVal;

    // ── Performance: skip geometry updates when idle and no breathing change ──
    const geometryInterval = this.options.geometryUpdateMs + this._perfMode * 28;
    const colorInterval = this.options.colorUpdateMs + this._perfMode * 32;
    const wantsGeometryUpdate = ev >= 0.005 || breathChanged || convState === "processing" || convState === "speaking" || convState === "listening";
    const needsGeometryUpdate = wantsGeometryUpdate && now - this._lastGeometryUpdate >= geometryInterval;

    if (needsGeometryUpdate) {
      this._lastGeometryUpdate = now;
      // Deform dot shell
      const dotPos = this.dots.geometry.attributes.position;
      for (let i = 0; i < dotPos.count; i++) {
        const v = this.originalVertices[i];
        const noise = this.simplex.noise3D(
          v.x * 0.62 + time * 1.25 + this._statePhase * 0.17,
          v.y * 0.67 - time * 0.72 + this._statePhaseB * 0.11,
          v.z * 0.59 + Math.sin(time * 0.8 + this._statePhase) * 0.55
        );
        const listeningShape = convState === "listening"
          ? 1 + stateShapeWarp * 2.5 * (
            Math.sin(now * 0.0019 + v.y * 1.05 + this._statePhase) * 0.44
            + Math.sin(now * 0.0031 + v.x * 0.72 + this._statePhaseB) * 0.31
            + (v.x / this.options.baseScale) * 0.26
            - (v.z / this.options.baseScale) * 0.19
          )
          : 1;
        const speechRipple = convState === "speaking"
          ? 0.15 * Math.sin(v.y * 3.2 - now * 0.012) * Math.cos(v.x * 2.2 + now * 0.009) * ev
          : 0;
        const d = listeningShape * (1 + (noise * 0.35 * wobbleStrength) + speechRipple);
        dotPos.setXYZ(i, v.x * d, v.y * d, v.z * d);
      }
      dotPos.needsUpdate = true;

      // Core and glass shell are permanently hidden for the stardust particle
      // sphere, so their geometry is never deformed and no normal recomputation
      // is required here.
    }

    // ── Audio-reactive vertex colors: hotspots expand and brighten ──
    const colorAttr = this.dots.geometry.attributes.color;
    if (now - this._lastColorUpdate >= colorInterval) {
      this._lastColorUpdate = now;
      this._computeVertexColors(colorAttr.array, time, ev, this._statePhase);
      colorAttr.needsUpdate = true;
    }

    // ── Audio-reactive dot size ──
    this.dots.material.size = 0.08 + ev * 0.04;

    // ── Swirling dynamic light orbits for organic reflections ──
    const tLight = now * 0.0006;
    const R = this.options.baseScale;
    this.lightViolet.position.set(
      -R * 0.6 + Math.sin(tLight) * 0.35,
      R * 0.65 + Math.cos(tLight * 0.8) * 0.35,
      R * 0.5 + Math.sin(tLight * 1.2) * 0.25
    );
    this.lightFuchsia.position.set(
      R * 0.5 + Math.cos(tLight * 1.1) * 0.35,
      R * 0.6 + Math.sin(tLight * 0.9) * 0.35,
      R * 0.55 + Math.cos(tLight * 0.7) * 0.25
    );
    this.lightAmber.position.set(
      R * 0.55 + Math.sin(tLight * 0.9) * 0.35,
      -R * 0.5 + Math.cos(tLight * 1.2) * 0.35,
      R * 0.6 + Math.sin(tLight * 0.8) * 0.25
    );

    // ── Audio-reactive lights: intensity and range boost ──
    const breathe = Math.sin(now * 0.001) * 0.2 + 1;
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
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }

    // Traverse and dispose of all Three.js resources to prevent memory leaks
    if (this.scene) {
      this.scene.traverse((object) => {
        if (object.geometry) {
          object.geometry.dispose();
        }
        if (object.material) {
          if (Array.isArray(object.material)) {
            object.material.forEach((mat) => mat.dispose());
          } else {
            object.material.dispose();
          }
        }
      });
    }

    if (this.renderer) {
      this.renderer.dispose();
    }

    if (this.container && this.renderer) {
      this.container.removeChild(this.renderer.domElement);
    }
  }
}
