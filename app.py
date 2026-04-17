import io
import os
import zipfile
from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB upload max

PYWEBVIEW_MAIN = '''import os
import webview

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(base_dir, 'index.html')
    webview.create_window('{app_name}', index_path)
    webview.start()
'''

ELECTRON_MAIN = '''const { app, BrowserWindow } = require('electron')
const path = require('path')

function createWindow() {
  const win = new BrowserWindow({
    width: 1024,
    height: 768,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  win.loadFile('index.html')
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})
'''

ELECTRON_PACKAGE_JSON = '''{
  "name": "{slug}",
  "productName": "{product_name}",
  "version": "{version}",
  "description": "Generated WebToExe app",
  "main": "main.js",
  "scripts": {
    "start": "electron ."
  },
  "dependencies": {},
  "devDependencies": {
    "electron": "^26.0.0"
  }
}
'''

ICON_PLACEHOLDER = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82'


def wrap_html_fragment(raw_html: str, title: str) -> str:
    normalized = raw_html.strip().lower()
    if normalized.startswith('<!doctype') or normalized.startswith('<html'):
        return raw_html
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body>
{raw_html}
</body>
</html>
'''


def build_site_page(title: str, body_html: str) -> str:
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f4f7fb; color: #1f2937; }}
    .topnav {{ background: #2563eb; color: #fff; padding: 12px 20px; display: flex; flex-wrap: wrap; gap: 12px; }}
    .topnav a {{ color: #fff; text-decoration: none; font-weight: 600; }}
    .content {{ padding: 24px; }}
    .page-frame {{ width: 100%; min-height: calc(100vh - 72px); border: none; }}
  </style>
</head>
<body>
  <nav class="topnav">
    <a href="index.html">Home</a>
    <a href="about.html">About</a>
    <a href="help.html">Help</a>
    <a href="contact.html">Contact</a>
  </nav>
  <main class="content">{body_html}</main>
</body>
</html>
'''


def sanitize_zip_path(file_path: str) -> str:
    normalized = file_path.replace('\\', '/').strip('/')
    parts = normalized.split('/')
    if not normalized or any(part == '..' or part == '' for part in parts):
        raise ValueError('Invalid zip entry path')
    return '/'.join(parts)


def extract_zip_files(zip_bytes: bytes) -> dict:
    files = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            try:
                path = sanitize_zip_path(info.filename)
            except ValueError:
                continue
            files[path] = zf.read(info)
    return files


def build_redirect_page(target: str) -> str:
    safe_target = target.replace('"', '\\"')
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Redirect</title>
</head>
<body>
  <script>window.location.replace("{safe_target}");</script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    app_name = request.form.get('app_name', 'WebToExeApp').strip() or 'WebToExeApp'
    package_name = request.form.get('package_name', '').strip() or app_name
    version = request.form.get('version', '1.0.0').strip() or '1.0.0'
    main_page = request.form.get('main_page', 'index.html').strip() or 'index.html'
    icon_upload = request.files.get('icon_file')
    source_zip = request.files.get('source_zip')
    source_type = request.form.get('source_type', 'url')
    wrapper_type = request.form.get('wrapper_type', 'pywebview')
    include_extra = bool(request.form.get('include_extra_pages'))
    raw_url = request.form.get('source_url', '').strip()
    raw_html = request.form.get('source_html', '').strip()

    safe_package = secure_filename(package_name).replace('-', '_') or 'webtoexe_app'
    safe_version = secure_filename(version) or '1.0.0'
    folder_name = safe_package

    if icon_upload and icon_upload.filename:
        safe_icon = secure_filename(icon_upload.filename) or 'icon.png'
        icon_bytes = icon_upload.read()
        if not icon_bytes:
            icon_bytes = ICON_PLACEHOLDER
    else:
        safe_icon = 'icon.png'
        icon_bytes = ICON_PLACEHOLDER

    escaped_app_name = app_name.replace('"', '\\"')

    if source_type == 'zip':
        if not source_zip or not source_zip.filename:
            return 'Error: ZIP file is required for ZIP source.', 400
        try:
            zip_data = source_zip.read()
            site_files = extract_zip_files(zip_data)
        except zipfile.BadZipFile:
            return 'Error: Uploaded file is not a valid zip archive.', 400
        if not site_files:
            return 'Error: ZIP archive is empty or contains no valid files.', 400

        if main_page not in site_files:
            if main_page == 'index.html' and 'index.html' not in site_files:
                html_files = [name for name in site_files if name.lower().endswith('.html')]
                if html_files:
                    main_page = html_files[0]
                else:
                    return 'Error: ZIP archive contains no HTML files.', 400
            else:
                return f'Error: Main page "{main_page}" not found in the uploaded ZIP.', 400

        if include_extra:
            iframe_target = main_page
            if main_page == 'index.html':
                site_files['site_index.html'] = site_files['index.html']
                iframe_target = 'site_index.html'
            site_files['index.html'] = build_site_page(app_name, f'<iframe src="{iframe_target}" class="page-frame"></iframe>')
            site_files['about.html'] = build_site_page(f'{app_name} - About', f'<h1>About</h1><p>This app was generated by WebToExe.</p><p>Package name: {safe_package}</p>')
            site_files['help.html'] = build_site_page(f'{app_name} - Help', '<h1>Help</h1><p>Use the navigation bar to browse pages and open the app.</p>')
            site_files['contact.html'] = build_site_page(f'{app_name} - Contact', '<h1>Contact</h1><p>Need more pages? Customize this generated bundle.</p>')
        else:
            if main_page != 'index.html':
                site_files['index.html'] = build_redirect_page(main_page)

    else:
        if source_type == 'url':
            if not raw_url:
                return 'Error: URL is required for URL source.', 400
        else:
            if not raw_html:
                return 'Error: HTML content is required for HTML source.', 400

        site_files = {}
        if include_extra:
            if source_type == 'url':
                main_body = f'<iframe src="{raw_url}" class="page-frame"></iframe>'
            else:
                site_files['content.html'] = wrap_html_fragment(raw_html, app_name)
                main_body = '<iframe src="content.html" class="page-frame"></iframe>'

            site_files['index.html'] = build_site_page(app_name, main_body)
            site_files['about.html'] = build_site_page(f'{app_name} - About', f'<h1>About</h1><p>This app was generated by WebToExe.</p><p>Package name: {safe_package}</p>')
            site_files['help.html'] = build_site_page(f'{app_name} - Help', '<h1>Help</h1><p>Use the navigation bar to browse pages and open the app.</p>')
            site_files['contact.html'] = build_site_page(f'{app_name} - Contact', '<h1>Contact</h1><p>Need more pages? Customize this generated bundle.</p>')
        else:
            if source_type == 'url':
                site_files['index.html'] = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{app_name}</title>
</head>
<body style="margin:0; height:100vh; overflow:hidden;">
  <iframe src="{raw_url}" frameborder="0" style="width:100%; height:100%;"></iframe>
</body>
</html>
'''
            else:
                site_files['index.html'] = wrap_html_fragment(raw_html, app_name)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_name, file_content in site_files.items():
            zip_file.writestr(f'{folder_name}/{file_name}', file_content)

        if wrapper_type == 'electron':
            main_js = ELECTRON_MAIN.replace(
                '  const win = new BrowserWindow({',
                f'  const win = new BrowserWindow({{
    icon: path.join(__dirname, "{safe_icon}"),'
            ) if safe_icon else ELECTRON_MAIN
            zip_file.writestr(f'{folder_name}/main.js', main_js)
            zip_file.writestr(
                f'{folder_name}/package.json',
                ELECTRON_PACKAGE_JSON.format(slug=safe_package.lower(), product_name=app_name.replace('"', '\\"'), version=safe_version)
            )
            zip_file.writestr(
                f'{folder_name}/{safe_icon}',
                icon_bytes
            )
            zip_file.writestr(
                f'{folder_name}/version.txt',
                safe_version
            )
            zip_file.writestr(
                f'{folder_name}/README.md',
                'Install dependencies with npm install and run with npm start.\nReplace the included icon file with your own icon if desired.'
            )
        else:
            if safe_icon:
                py_main = f'''import os
import webview

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(base_dir, 'index.html')
    webview.create_window("{escaped_app_name}", index_path, icon=os.path.join(base_dir, "{safe_icon}"))
    webview.start()
'''
            else:
                py_main = PYWEBVIEW_MAIN.format(app_name=escaped_app_name)

            zip_file.writestr(
                f'{folder_name}/main.py',
                py_main
            )
            if safe_icon:
                zip_file.writestr(
                    f'{folder_name}/{safe_icon}',
                    icon_bytes
                )
            zip_file.writestr(
                f'{folder_name}/requirements.txt',
                'pywebview>=3.9.0\n'
            )
            zip_file.writestr(
                f'{folder_name}/version.txt',
                safe_version
            )
            zip_file.writestr(
                f'{folder_name}/README.md',
                f'App Name: {app_name}\nVersion: {safe_version}\nRun with: python main.py\nInstall dependencies with: pip install -r requirements.txt\nReplace the included icon file with your own icon if desired.'
            )

    zip_buffer.seek(0)
    zip_name = f'{folder_name}_webtoexe.zip'
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=zip_name,
        mimetype='application/zip'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
