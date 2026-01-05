import { Command } from "@tauri-apps/plugin-shell";

let backend = null;

async function startBackend() {
  backend = await Command.create("sidecar", [], {
    cwd: "../backend",
  }).spawn();
}

window.addEventListener("DOMContentLoaded", async () => {
  await startBackend();

  // Give backend a moment to boot
  setTimeout(() => {
    window.location.href = "http://127.0.0.1:8000/";
  }, 1500);
});
