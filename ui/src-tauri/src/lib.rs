#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Command, Stdio};

pub fn run() {
  tauri::Builder::default()
    .setup(|_app| {
      #[cfg(target_os = "windows")]
      {
        use std::fs::OpenOptions;
        use std::os::windows::process::CommandExt;

        // Points to: ...\ui\src-tauri
        let manifest_dir = env!("CARGO_MANIFEST_DIR");

        // Absolute paths to backend + venv python
        let backend_dir = format!(r"{}\..\..\backend", manifest_dir);
        let python_exe = format!(r"{}\.venv\Scripts\python.exe", backend_dir);

        // Log files so we can debug startup
        let out_path = format!(r"{}\backend_out.log", backend_dir);
        let err_path = format!(r"{}\backend_err.log", backend_dir);

        let out_file = OpenOptions::new()
          .create(true)
          .append(true)
          .open(&out_path)
          .unwrap();

        let err_file = OpenOptions::new()
          .create(true)
          .append(true)
          .open(&err_path)
          .unwrap();

        let mut cmd = Command::new(python_exe);
        cmd.current_dir(&backend_dir);
        cmd.args([
          "-m", "uvicorn",
          "main:app",
          "--host", "127.0.0.1",
          "--port", "8000",
        ]);

        cmd.stdout(Stdio::from(out_file));
        cmd.stderr(Stdio::from(err_file));

        // Hide console window
        cmd.creation_flags(0x08000000);

        match cmd.spawn() {
  Ok(_child) => {
    std::fs::write(
      format!(r"{}\tauri_spawn_ok.log", backend_dir),
      "spawn ok\n"
    ).ok();
  }
  Err(e) => {
    std::fs::write(
      format!(r"{}\tauri_spawn_err.log", backend_dir),
      format!("spawn error: {}\n", e)
    ).ok();
  }
}
      }

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
