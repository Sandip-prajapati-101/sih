// 3D viewer: loads the .glb/.gltf that the AI (or offline engine) selected.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const container = document.getElementById("modelViewer");
let renderer, scene, camera, controls, holder;
const loader = new GLTFLoader();

function init() {
  if (renderer) return;
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, 0.8, 4);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.innerHTML = "";
  container.appendChild(renderer.domElement);

  scene.add(new THREE.HemisphereLight(0xffffff, 0x555566, 1.1));
  const dir = new THREE.DirectionalLight(0xffffff, 1.4);
  dir.position.set(3, 5, 4);
  scene.add(dir);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 2.0;
  controls.enablePan = false;

  new ResizeObserver(resize).observe(container);
  resize();
  renderer.setAnimationLoop(() => {
    controls.update();
    renderer.render(scene, camera);
  });
}

function resize() {
  const w = container.clientWidth || 400;
  const h = container.clientHeight || 340;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

function clearHolder() {
  if (!holder) return;
  scene.remove(holder);
  holder.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose());
  });
  holder = null;
}

function fitAndShow(obj) {
  // centre + scale the model so any file size fits the view
  const box = new THREE.Box3().setFromObject(obj);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  obj.position.sub(center);
  holder = new THREE.Group();
  holder.add(obj);
  holder.scale.setScalar(2 / (Math.max(size.x, size.y, size.z) || 1));
  scene.add(holder);
}

// Simple stand-in shape if the file is missing or fails to load
function fallbackMesh(shape) {
  const mat = new THREE.MeshStandardMaterial({ color: 0x4f8cff, roughness: 0.4, metalness: 0.2 });
  let geo;
  switch (shape) {
    case "bottle": geo = new THREE.CylinderGeometry(0.5, 0.5, 1.6, 32); break;
    case "jar": geo = new THREE.CylinderGeometry(0.7, 0.7, 1.0, 32); break;
    case "cardboard_box": geo = new THREE.BoxGeometry(1.4, 1.0, 1.0); break;
    case "flow_wrap": geo = new THREE.BoxGeometry(1.8, 0.5, 0.8); break;
    case "bulk_bag": geo = new THREE.CylinderGeometry(0.75, 0.55, 1.9, 24); break;
    default: geo = new THREE.BoxGeometry(1.1, 1.6, 0.35);
  }
  return new THREE.Mesh(geo, mat);
}

window.loadPackagingModel = function (url, shape) {
  init();
  clearHolder();
  if (!url) { fitAndShow(fallbackMesh(shape)); return; }

  loader.load(
    url,
    (gltf) => { clearHolder(); fitAndShow(gltf.scene); },
    undefined,
    (err) => {
      console.warn("3D model failed to load, using fallback shape:", err);
      clearHolder();
      fitAndShow(fallbackMesh(shape));
    }
  );
};

// If the result arrived before this module finished loading
if (window.__pendingModel) {
  window.loadPackagingModel(...window.__pendingModel);
  window.__pendingModel = null;
}
