// Romeo 3D character: replaces the status orb when a .glb model is available.
//
// How it reacts to Romeo's state (idle / awake / listening / thinking / speaking / follow_up / stopped):
//  - animation clips in the model are played by name when they exist
//    (e.g. "Idle", "Wave", "Listen", "Think", "Talk") with smooth cross-fades;
//  - on top of that, gentle procedural motion (breathing, lean-in, head tilt, bounce);
//  - a coloured rim light uses the same colours as the orb (blue/purple/green/red);
//  - shape keys for the mouth (jawOpen, mouthOpen, viseme_aa, A…) move while speaking,
//    and blink shape keys blink every few seconds.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

const STATE_COLORS = {
  idle: 0x9ca3af, awake: 0x2f80ed, listening: 0x2f80ed, follow_up: 0x2f80ed,
  thinking: 0x8b5cf6, speaking: 0x10b981, stopped: 0xe5484d,
};

// Clip-name patterns per state, first match wins. "idle" is the fallback for every state.
const CLIP_PATTERNS = {
  awake: [/wave|greet|hello|hi\b|nod|alert/i],
  listening: [/listen|attent|alert|lean/i],
  follow_up: [/listen|attent|alert/i],
  thinking: [/think|ponder|wonder|consider|hmm/i],
  speaking: [/talk|speak|say|explain|chat|convers/i],
  stopped: [/stop|sad|bow|off|sleep/i],
  idle: [/idle|breath|stand|rest|default/i],
};

// Procedural motion per state: bob height, bob speed, sway, forward lean, head tilt speed.
const MOTION = {
  idle:      { bob: 0.008, speed: 1.2, sway: 0.05, lean: 0.0,  tilt: 0.0 },
  awake:     { bob: 0.02,  speed: 3.0, sway: 0.0,  lean: 0.06, tilt: 0.0 },
  listening: { bob: 0.01,  speed: 1.6, sway: 0.0,  lean: 0.08, tilt: 0.0 },
  follow_up: { bob: 0.01,  speed: 1.6, sway: 0.02, lean: 0.05, tilt: 0.0 },
  thinking:  { bob: 0.006, speed: 1.0, sway: 0.0,  lean: 0.0,  tilt: 0.6 },
  speaking:  { bob: 0.018, speed: 5.0, sway: 0.03, lean: 0.03, tilt: 0.0 },
  stopped:   { bob: 0.0,   speed: 0.0, sway: 0.0,  lean: -0.04, tilt: 0.0 },
};

const MOUTH = /jaw_?open|mouth_?open|viseme_?aa|^aa$|^a$|mouth_?a\b|vrc\.v_aa|fcl_mth_a/i;
const BLINK = /blink|eyes?_?closed?|fcl_eye_close/i;

function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch (_) { return false; }
}

export async function startAvatar({ container, token, onStatus = () => {} }) {
  const headers = { "X-Romeo-Token": token || "" };
  const info = await fetch("/api/model", { headers }).then((r) => (r.ok ? r.json() : { available: false }));
  if (!info.available) return null;
  if (!webglAvailable()) { onStatus("เบราว์เซอร์นี้แสดงโมเดล 3D ไม่ได้ (ไม่มี WebGL)"); return null; }

  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const canvas = document.createElement("canvas");
  canvas.className = "avatar-canvas";
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "Romeo");
  container.append(canvas);

  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(28, 1, 0.01, 100);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x445066, 1.1));
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(1.5, 2.5, 3);
  scene.add(key);
  const rim = new THREE.PointLight(STATE_COLORS.idle, 0, 10);
  rim.position.set(-1.2, 1.4, -1.5);
  scene.add(rim);

  // ---- load ----
  onStatus(`กำลังโหลดโมเดล ${info.name} (${(info.size / 1048576).toFixed(1)} MB)…`);
  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath("/static/vendor/three/addons/libs/draco/gltf/");
  loader.setDRACOLoader(draco);
  loader.setMeshoptDecoder(MeshoptDecoder);
  const url = `${info.url}?token=${encodeURIComponent(token || "")}`;
  let gltf;
  try {
    gltf = await loader.loadAsync(url, (e) => {
      if (e.total) onStatus(`กำลังโหลดโมเดล… ${Math.round((e.loaded / e.total) * 100)}%`);
    });
  } catch (err) {
    canvas.remove();
    onStatus("โหลดโมเดล 3D ไม่ได้: " + (err?.message || err));
    return null;
  }

  // Centre the model on the floor and frame it.
  const model = gltf.scene;
  const pivot = new THREE.Group();
  pivot.add(model);
  scene.add(pivot);
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const scale = 1.6 / Math.max(size.y, size.x, size.z, 1e-6);
  model.scale.setScalar(scale);
  model.position.set(-center.x * scale, -box.min.y * scale, -center.z * scale);
  const height = size.y * scale;
  const target = new THREE.Vector3(0, height * 0.55, 0);
  const fitDist = (height * 0.62) / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  camera.position.set(0, target.y + height * 0.05, fitDist);
  camera.lookAt(target);

  // ---- animation clips ----
  const mixer = gltf.animations.length ? new THREE.AnimationMixer(model) : null;
  const actions = new Map();
  for (const clip of gltf.animations) actions.set(clip.name, mixer.clipAction(clip));
  function clipFor(state) {
    const names = [...actions.keys()];
    for (const re of [...(CLIP_PATTERNS[state] || []), ...CLIP_PATTERNS.idle]) {
      const hit = names.find((n) => re.test(n));
      if (hit) return actions.get(hit);
    }
    return names.length ? actions.get(names[0]) : null; // something is better than a T-pose
  }

  // ---- shape keys (mouth / blink) ----
  const mouth = [], blink = [];
  model.traverse((o) => {
    if (!o.isMesh || !o.morphTargetDictionary) return;
    for (const [name, i] of Object.entries(o.morphTargetDictionary)) {
      if (MOUTH.test(name)) mouth.push([o, i]);
      else if (BLINK.test(name)) blink.push([o, i]);
    }
  });

  // ---- state handling ----
  let state = "idle", current = null;
  const motion = { ...MOTION.idle };
  const rimColor = new THREE.Color(STATE_COLORS.idle);
  function setState(next) {
    state = MOTION[next] ? next : "idle";
    rimColor.setHex(STATE_COLORS[state] ?? STATE_COLORS.idle);
    const action = clipFor(state);
    if (action && action !== current) {
      action.reset().setEffectiveWeight(1).fadeIn(0.35).play();
      if (current) current.fadeOut(0.35);
      current = action;
    }
    if (mixer) mixer.timeScale = state === "stopped" ? 0.0 : 1.0;
  }
  setState("idle");

  // ---- render loop ----
  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(container);
  resize();

  const clock = new THREE.Clock();
  let t = 0, nextBlink = 2 + Math.random() * 3, blinkT = -1;
  renderer.setAnimationLoop(() => {
    const dt = Math.min(clock.getDelta(), 0.1);
    t += dt;
    if (mixer) mixer.update(dt);

    // ease procedural parameters toward the current state
    const goal = MOTION[state];
    for (const k of Object.keys(goal)) motion[k] += (goal[k] - motion[k]) * Math.min(1, dt * 4);
    const damp = reduceMotion ? 0.25 : 1;
    pivot.position.y = Math.sin(t * motion.speed) * motion.bob * height * damp;
    pivot.rotation.y = Math.sin(t * 0.5) * motion.sway * damp;
    pivot.rotation.x = motion.lean * damp;
    pivot.rotation.z = Math.sin(t * motion.tilt) * 0.06 * Math.min(motion.tilt, 1) * damp;

    // rim light follows the state colour
    rim.color.lerp(rimColor, Math.min(1, dt * 6));
    const glow = state === "idle" ? 0.4 : state === "speaking" ? 2.2 + Math.sin(t * 9) * 0.6 : 1.8;
    rim.intensity += (glow * 3 - rim.intensity) * Math.min(1, dt * 5);

    // mouth while speaking
    const open = state === "speaking" && !reduceMotion
      ? Math.max(0, Math.sin(t * 13) * 0.5 + Math.sin(t * 7.3) * 0.35 + 0.15) : 0;
    for (const [mesh, i] of mouth) {
      mesh.morphTargetInfluences[i] += (open - mesh.morphTargetInfluences[i]) * Math.min(1, dt * 18);
    }
    // blink
    if (blink.length) {
      if (blinkT < 0 && t > nextBlink) blinkT = 0;
      if (blinkT >= 0) {
        blinkT += dt;
        const v = blinkT < 0.08 ? blinkT / 0.08 : Math.max(0, 1 - (blinkT - 0.08) / 0.1);
        for (const [mesh, i] of blink) mesh.morphTargetInfluences[i] = v;
        if (blinkT > 0.2) { blinkT = -1; nextBlink = t + 2.5 + Math.random() * 3.5; }
      }
    }
    renderer.render(scene, camera);
  });

  onStatus("");
  return {
    setState,
    info: { name: info.name, clips: [...actions.keys()], mouth: mouth.length, blink: blink.length },
  };
}
