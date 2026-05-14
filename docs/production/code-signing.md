# Code-Signing für Lexa AI

## Warum Code-Signing?

Windows SmartScreen blockiert unsignierte .exe-Dateien. Benutzer sehen:
- "Windows hat Ihren PC geschützt" Dialog
- "Unbekannter Herausgeber" Warnung
- Möglicherweise wird der Download blockiert

Ein Code-Signing-Zertifikat eliminiert diese Warnungen.

## Optionen

### Option 1: EV Code-Signing-Zertifikat (Empfohlen)
- **Anbieter**: DigiCert, Sectigo, GlobalSign
- **Kosten**: ~400-500 EUR/Jahr
- **Vorteile**: Sofortige SmartScreen-Reputation, Hardware-Token
- **Setup**:
  1. Zertifikat bestellen (Firmenverifizierung nötig)
  2. Hardware-Token (USB) erhalten
  3. In electron-builder.json konfigurieren

### Option 2: OV Code-Signing-Zertifikat
- **Anbieter**: Sectigo, Comodo, SSL.com
- **Kosten**: ~200-300 EUR/Jahr
- **Vorteile**: Günstiger als EV
- **Nachteile**: SmartScreen-Reputation muss aufgebaut werden (Downloads)

### Option 3: Selbstsigniert (nur Entwicklung)
- **Kosten**: Kostenlos
- **Nachteile**: SmartScreen warnt weiterhin, keine Vertrauenskette

## Einrichtung

### 1. electron-builder.json anpassen

Aktuelle Konfiguration in `frontend/electron-builder.json` hat bereits `forceCodeSigning: false` und `signAndEditExecutable: false`. Um Code-Signing zu aktivieren, die `win`-Sektion ersetzen:

```json
{
  "win": {
    "target": [{"target": "nsis", "arch": ["x64"]}],
    "icon": "src/icon.ico",
    "forceCodeSigning": true,
    "signingHashAlgorithms": ["sha256"],
    "certificateFile": "${env.WIN_CSC_LINK}",
    "certificatePassword": "${env.WIN_CSC_KEY_PASSWORD}"
  }
}
```

**Wichtig:** Ohne gesetzte Umgebungsvariablen schlägt der Build fehl wenn `forceCodeSigning: true`. Daher bleibt die aktuelle Config bei `false` bis ein Zertifikat vorhanden ist.

### 2. Umgebungsvariablen setzen

```bash
# Lokal (Entwicklung)
set WIN_CSC_LINK=pfad/zum/zertifikat.pfx
set WIN_CSC_KEY_PASSWORD=dein-passwort

# GitHub Actions (Secrets)
# Settings > Secrets > Actions:
# WIN_CSC_LINK: Base64-encoded .pfx Datei
# WIN_CSC_KEY_PASSWORD: Zertifikat-Passwort
```

### 3. GitHub Actions Release-Workflow anpassen

In `.github/workflows/release.yml` die Signing-Variablen ergänzen:

```yaml
- name: Build & Sign
  env:
    WIN_CSC_LINK: ${{ secrets.WIN_CSC_LINK }}
    WIN_CSC_KEY_PASSWORD: ${{ secrets.WIN_CSC_KEY_PASSWORD }}
  run: npm run build
```

### 4. SignTool für PyInstaller-Backend

Das Backend (.exe via PyInstaller) muss separat signiert werden:

```powershell
# Nach PyInstaller-Build, vor Electron-Builder
signtool sign /f "zertifikat.pfx" /p "passwort" /t http://timestamp.digicert.com /fd sha256 backend-dist/lexa-backend/lexa-backend.exe
```

## CI/CD Integration

### GitHub Actions mit Code-Signing

```yaml
name: Release
on:
  push:
    tags: ['v*']

jobs:
  build-and-release:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Build Backend
        run: python build_backend.py

      - name: Sign Backend
        if: env.WIN_CSC_LINK != ''
        env:
          WIN_CSC_LINK: ${{ secrets.WIN_CSC_LINK }}
          WIN_CSC_KEY_PASSWORD: ${{ secrets.WIN_CSC_KEY_PASSWORD }}
        run: |
          # Decode certificate
          echo $env:WIN_CSC_LINK | base64 -d > cert.pfx
          # Sign backend exe
          & "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe" sign /f cert.pfx /p $env:WIN_CSC_KEY_PASSWORD /t http://timestamp.digicert.com /fd sha256 backend-dist/lexa-backend/lexa-backend.exe
          Remove-Item cert.pfx

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20

      - name: Install & Build Electron
        working-directory: frontend
        env:
          WIN_CSC_LINK: ${{ secrets.WIN_CSC_LINK }}
          WIN_CSC_KEY_PASSWORD: ${{ secrets.WIN_CSC_KEY_PASSWORD }}
        run: |
          npm install
          npm run build

      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/*.exe
          generate_release_notes: true
```

## Kosten-Zusammenfassung

| Option | Kosten/Jahr | SmartScreen | Empfehlung |
|--------|------------|-------------|------------|
| EV Zertifikat | ~450 EUR | Sofort | Professionelle Apps |
| OV Zertifikat | ~250 EUR | Aufbau nötig | Budget-Option |
| Selbstsigniert | 0 EUR | Warnung | Nur Entwicklung |

## Nächste Schritte

1. Budget für Code-Signing-Zertifikat klären
2. EV oder OV Zertifikat bestellen
3. GitHub Secrets konfigurieren (WIN_CSC_LINK, WIN_CSC_KEY_PASSWORD)
4. electron-builder.json: `forceCodeSigning` auf `true` setzen
5. Release-Workflow testen
6. SmartScreen-Reputation aufbauen (bei OV)
