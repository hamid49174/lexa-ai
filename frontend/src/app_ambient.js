/* App ambient canvas helpers. Classic script loaded before app.js. */

let _ambientCanvasRaf = 0;

function initLexaAmbientCanvas() {
  const canvas = document.getElementById("lexa-ambient-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return;

  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  let width = 0;
  let height = 0;
  let frame = 0;

  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = Math.max(1, window.innerWidth);
    height = Math.max(1, window.innerHeight);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };

  const draw = (time = 0) => {
    if (document.hidden) {
      if (!reducedMotion) _ambientCanvasRaf = requestAnimationFrame(draw);
      return;
    }
    frame += 1;
    const tWave = reducedMotion ? 18 : time * 0.00035;
    ctx.clearRect(0, 0, width, height);

    const bg = ctx.createLinearGradient(0, 0, width, height);
    bg.addColorStop(0, "rgba(7, 11, 18, 0.96)");
    bg.addColorStop(0.48, "rgba(9, 9, 16, 0.98)");
    bg.addColorStop(1, "rgba(7, 15, 18, 0.96)");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, width, height);

    const gap = 44;
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(255, 255, 255, 0.018)";
    for (let x = -gap; x < width + gap; x += gap) {
      const drift = Math.sin(tWave + x * 0.01) * 8;
      ctx.beginPath();
      ctx.moveTo(x + drift, 0);
      ctx.lineTo(x - drift * 0.3, height);
      ctx.stroke();
    }
    for (let y = -gap; y < height + gap; y += gap) {
      const drift = Math.cos(tWave + y * 0.012) * 7;
      ctx.beginPath();
      ctx.moveTo(0, y + drift);
      ctx.lineTo(width, y - drift * 0.25);
      ctx.stroke();
    }

    const waveColors = [
      "rgba(91, 124, 250, 0.085)",
      "rgba(16, 185, 129, 0.06)",
      "rgba(194, 77, 224, 0.055)",
    ];
    for (let line = 0; line < 8; line += 1) {
      const base = height * (0.28 + line * 0.07);
      ctx.beginPath();
      for (let x = -20; x <= width + 20; x += 18) {
        const y = base
          + Math.sin(x * 0.009 + tWave * (1.6 + line * 0.08) + line) * (18 + line * 2)
          + Math.cos(x * 0.004 + tWave * 1.2) * 12;
        if (x === -20) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = waveColors[line % waveColors.length];
      ctx.lineWidth = line % 3 === 0 ? 0.85 : 0.62;
      ctx.stroke();
    }

    const topShade = ctx.createLinearGradient(0, 0, 0, height * 0.22);
    topShade.addColorStop(0, "rgba(5, 6, 11, 0.72)");
    topShade.addColorStop(1, "rgba(5, 6, 11, 0)");
    ctx.fillStyle = topShade;
    ctx.fillRect(0, 0, width, height * 0.24);

    const vignette = ctx.createRadialGradient(width * 0.5, height * 0.42, 0, width * 0.5, height * 0.42, Math.max(width, height) * 0.72);
    vignette.addColorStop(0, "rgba(255, 255, 255, 0.035)");
    vignette.addColorStop(0.58, "rgba(0, 0, 0, 0.02)");
    vignette.addColorStop(1, "rgba(0, 0, 0, 0.46)");
    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, width, height);

    window.__lexaAmbientDebug = { frame, width, height, reducedMotion: Boolean(reducedMotion) };
    if (!reducedMotion) _ambientCanvasRaf = requestAnimationFrame(draw);
  };

  resize();
  window.addEventListener("resize", () => {
    resize();
    if (reducedMotion) draw(0);
  });
  if (_ambientCanvasRaf) cancelAnimationFrame(_ambientCanvasRaf);
  draw(0);
}
