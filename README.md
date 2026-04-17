# WebToExe

WebToExe is a simple web-based tool for generating a webview wrapper from a URL or HTML content.

## What it does

- Accepts a URL or raw HTML
- Generates a downloadable app bundle
- Supports Python + `pywebview` or Electron wrapper skeletons

## Run locally

1. Install dependencies:
   ```bash
   python3 -m pip install -r requirements.txt
   ```
2. Start the web app:
   ```bash
   python app.py
   ```
3. Open your browser at `http://127.0.0.1:5000`

## Usage

- Enter an app name
- Set the package name for generated project metadata
- Upload an icon file to include in the generated package
- Choose whether to include extra pages like About, Help, and Contact
- Choose wrapper type
- Provide a target URL or paste HTML
- Download the generated zip archive

## Notes

- The Python wrapper uses a generated `main.py` and `index.html` file.
- The Electron wrapper produces an Electron project skeleton with `package.json`, `main.js`, and `index.html`.
