# Build Troubleshooting - Lexa AI

## PyInstaller (Backend)

### Install Build Tooling
```bash
venv\Scripts\pip install -r requirements-dev.txt
```

### Build Command
```bash
python build_backend.py
```

Output: `backend-dist/lexa-backend/lexa-backend.exe`

### Common Issues

#### Missing Module
```text
ModuleNotFoundError: No module named 'xyz'
```

Fix: add it to `hiddenimports` in `build_backend.py`.

```python
hiddenimports = ["xyz"]
```

#### DLL Not Found
```text
FileNotFoundError: Could not find module 'xxx.dll'
```

Fix: add it to `datas` or `binaries` in the PyInstaller spec.

#### Large Bundle Size
- Use `--exclude-module` for unused packages
- Check whether test files are being included
- Use UPX compression when available

### Verification
```bash
cd backend-dist/lexa-backend
./lexa-backend.exe
# Should show: Uvicorn running on http://127.0.0.1:8000
curl http://127.0.0.1:8000/health
```

---

## Electron Builder (Frontend)

### Build Command
```bash
cd frontend
npm run build
```

Output: `dist/Lexa-AI-Setup-X.Y.Z.exe`

### Configuration
See `frontend/electron-builder.json` for NSIS installer settings.

### Common Issues

#### Icon Not Found
```text
Error: Cannot find icon
```

Fix: ensure `frontend/src/icon.png` and `frontend/src/icon.ico` exist.

#### Code Signing
For distribution outside your machine, you may want to sign the exe.
Without signing, Windows SmartScreen may warn users.

#### asar Packaging
Electron-builder packages the app into `asar` by default. If backend binaries need to stay outside `asar`:

```json
"asarUnpack": ["backend-dist/**"]
```

### Verification
1. Run the installer on a clean Windows VM.
2. Check that the backend starts on port 8000.
3. Check that the frontend connects.
4. Test core features like chat, voice, and commands.

---

## GitHub Actions CI/CD

### CI Pipeline (`ci.yml`)
Four jobs run on every push or PR:
1. `test-backend` - `pytest` on Windows
2. `test-frontend` - Node.js tests on Windows
3. `lint` - Python linting
4. `build` - `electron-builder` on the main branch

### Release Pipeline (`release.yml`)
Triggered on `v*` tags:
1. Build backend with PyInstaller
2. Build frontend with electron-builder
3. Create a GitHub Release with the installer attached

### Triggering a Release
```bash
git tag -a v0.21.0 -m "Release v0.21.0: Description"
git push origin v0.21.0
```

---

## Version Checklist

When bumping version, update all of these:
- [ ] `frontend/package.json` - `"version": "X.Y.Z"`
- [ ] `backend/config.py` - `VERSION = "X.Y.Z"`
- [ ] `start.bat` - version display
- [ ] `README.md` - public version references
- [ ] `docs/README.md` - current doc map and archive structure
- [ ] `frontend/src/index.html` - sidebar version tag if present
