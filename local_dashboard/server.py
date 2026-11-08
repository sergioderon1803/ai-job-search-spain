"""Local dashboard for the file-based job search workspace."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / 'job_search_tracker.csv'
JOBS = ROOT / 'job_scraper' / 'seen_jobs.json'
PROFILE = ROOT / '.claude' / 'skills' / 'job-application-assistant' / '01-candidate-profile.md'
HTML = Path(__file__).with_name('index.html')
HEADER = 'date,company,sector,role,role_type,channel,status,contact_person,fit_rating,notes,cv_file,cover_letter_file,source,deadline'
FIELDS = HEADER.split(',')
EDITABLE = {'date', 'company', 'sector', 'role', 'role_type', 'channel', 'status', 'contact_person', 'fit_rating', 'notes', 'source', 'deadline'}
STATUSES = {'drafted', 'applied', 'interview', 'offer', 'hired', 'rejected', 'no_response', 'offer_declined', 'withdrawn'}
TOKEN = secrets.token_urlsafe(32)
WRITE_LOCK = threading.Lock()


def profile_fields(title, content):
    """Expose editable values while keeping Markdown structure on the server."""
    fields, table_headers = [], None
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('|'):
            cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
            if i + 1 < len(lines) and re.match(r'^\|[\s|:\-]+\|\s*$', lines[i + 1]):
                table_headers = cells
            elif re.match(r'^\|[\s|:\-]+\|\s*$', line):
                continue
            elif table_headers and len(cells) == len(table_headers):
                for j, (label, value) in enumerate(zip(table_headers, cells)):
                    fields.append({'id': f'{i}:{j}', 'label': label, 'group': f'Fila {sum(1 for x in lines[:i] if x.startswith("|")) - 1}', 'value': value, 'kind': 'table'})
            continue
        table_headers = None
        if line.startswith('### ') and title == 'Professional Experience':
            fields.append({'id': f'{i}:heading', 'label': 'Puesto, empresa y periodo', 'group': 'Experiencia', 'value': line[4:], 'kind': 'heading'})
        elif match := re.match(r'^- \*\*(.+?):\*\*\s*(.*)$', line):
            fields.append({'id': f'{i}:bold', 'label': match.group(1), 'group': '', 'value': match.group(2), 'kind': 'bold'})
        elif line.startswith('- '):
            fields.append({'id': f'{i}:bullet', 'label': 'Detalle', 'group': '', 'value': line[2:], 'kind': 'bullet'})
        elif line and not line.startswith(('#', '<!--')):
            fields.append({'id': f'{i}:text', 'label': 'Descripción', 'group': '', 'value': line, 'kind': 'text'})
    return fields


def profile_data():
    raw = PROFILE.read_bytes() if PROFILE.exists() else b''
    text = raw.decode('utf-8-sig')
    matches = list(re.finditer(r'^## ([^\r\n]+)\s*$', text, re.MULTILINE))
    sections = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = match.group(1).strip()
        content = text[match.end():end].strip()
        sections.append({'title': title, 'content': content, 'fields': profile_fields(title, content)})
    return sections, hashlib.sha256(raw).hexdigest()


def write_profile_section(data):
    sections, version = profile_data()
    if data.get('version') != version:
        raise FileExistsError('El perfil ha cambiado. Recarga la página antes de guardar.')
    index, values = data.get('index'), data.get('values')
    if type(index) is not int or not 0 <= index < len(sections) or not isinstance(values, dict):
        raise ValueError('Sección no válida.')
    section = sections[index]
    allowed = {field['id']: field for field in section['fields']}
    if set(values) != set(allowed):
        raise ValueError('Los campos del perfil han cambiado. Recarga antes de guardar.')
    lines = section['content'].splitlines()
    table_edits = {}
    for key, value in values.items():
        field = allowed[key]
        if not isinstance(value, str) or any(c in value for c in '\r\n'):
            raise ValueError('Cada campo debe ocupar una sola línea.')
        if field['kind'] == 'table' and '|' in value:
            raise ValueError('El carácter | no está permitido en las tablas.')
        if value == field['value']:
            continue
        lineno = int(key.split(':')[0])
        if field['kind'] == 'table':
            table_edits.setdefault(lineno, {})[int(key.split(':')[1])] = value
        elif field['kind'] == 'bold':
            lines[lineno] = re.sub(r'^(- \*\*.+?:\*\*\s*).*$', lambda m: m.group(1) + value, lines[lineno])
        elif field['kind'] == 'bullet':
            lines[lineno] = '- ' + value
        elif field['kind'] == 'heading':
            lines[lineno] = '### ' + value
        else:
            if value.startswith(('#', '|', '- ')):
                raise ValueError('El texto no puede comenzar con un marcador Markdown.')
            lines[lineno] = value
    for lineno, edits in table_edits.items():
        cells = [c.strip() for c in lines[lineno].strip().strip('|').split('|')]
        for col, value in edits.items():
            cells[col] = value
        lines[lineno] = '| ' + ' | '.join(cells) + ' |'
    content = '\n'.join(lines)
    text = PROFILE.read_text(encoding='utf-8-sig')
    matches = list(re.finditer(r'^## ([^\r\n]+)\s*$', text, re.MULTILINE))
    start = matches[index].end()
    end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
    updated = text[:start] + '\n\n' + content.strip() + '\n\n' + text[end:]
    fd, temp = tempfile.mkstemp(dir=PROFILE.parent, prefix='.profile-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(updated)
        os.replace(temp, PROFILE)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_tracker():
    raw = TRACKER.read_bytes() if TRACKER.exists() else b''
    version = hashlib.sha256(raw).hexdigest()
    if not raw:
        return FIELDS[:], [], version, []
    text = raw.decode('utf-8-sig')
    lines = text.splitlines(keepends=True)
    parsed = list(csv.reader(io.StringIO(text, newline=''), strict=True))
    if not parsed:
        return FIELDS[:], [], version, []
    if len(parsed) != len(lines):
        raise ValueError('El CSV contiene campos multilínea; no se puede editar con seguridad.')
    fields = parsed[0]
    if len(fields) != len(set(fields)) or not {'company', 'role', 'status'}.issubset(fields):
        raise ValueError('La cabecera del CSV no es compatible.')
    if any(len(row) > len(fields) for row in parsed[1:]):
        raise ValueError('Una fila tiene más campos que la cabecera; revisa el CSV antes de editarlo.')
    rows = [dict(zip(fields, row + [''] * (len(fields) - len(row)))) for row in parsed[1:]]
    return fields, rows, version, lines


def write_entry(data):
    fields, rows, version, lines = read_tracker()
    if data.get('version') != version:
        raise FileExistsError('El archivo ha cambiado. Recarga la página antes de guardar.')
    values = data.get('values')
    if not isinstance(values, dict) or any(k not in EDITABLE for k in values):
        raise ValueError('Campos no válidos.')
    for value in values.values():
        if not isinstance(value, str) or any(c in value for c in ',"\r\n'):
            raise ValueError('No se permiten comas, comillas ni saltos de línea para mantener la compatibilidad del CSV.')
    index = data.get('index')
    is_new = index is None
    if not is_new and (type(index) is not int or index < 0 or index >= len(rows)):
        raise ValueError('La candidatura ya no existe.')
    row = {field: '' for field in fields} if is_new else dict(rows[index])
    if not set(values).issubset(fields):
        raise ValueError('El CSV no contiene todos los campos editados.')
    old_status = row.get('status', '')
    row.update(values)
    if not row.get('company', '').strip() or not row.get('role', '').strip():
        raise ValueError('Empresa y puesto son obligatorios.')
    if row.get('status') not in STATUSES:
        raise ValueError('Selecciona un estado válido.')
    if old_status == 'drafted' and row['status'] != 'drafted' and (not row.get('date') or 'date' not in values):
        raise ValueError('Indica la fecha real de envío al cambiar un borrador a otro estado.')
    for key in ('date', 'deadline'):
        if row.get(key):
            from datetime import date
            try:
                if date.fromisoformat(row[key]).isoformat() != row[key]:
                    raise ValueError()
            except ValueError:
                raise ValueError('Las fechas deben tener formato AAAA-MM-DD.')
    output = io.StringIO(newline='')
    csv.writer(output, lineterminator='\n').writerow([row.get(field, '') for field in fields])
    encoded = output.getvalue()
    if not lines:
        result = ','.join(fields) + '\n' + encoded
    elif is_new:
        existing = ''.join(lines)
        result = existing + ('' if existing.endswith(('\n', '\r')) else '\n') + encoded
    else:
        lines[index + 1] = encoded
        result = ''.join(lines)
    fd, temp = tempfile.mkstemp(dir=ROOT, prefix='.tracker-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(result)
        os.replace(temp, TRACKER)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_data():
    fields, rows, version, _ = read_tracker()
    jobs = []
    if JOBS.exists():
        doc = json.loads(JOBS.read_text(encoding='utf-8-sig'))
        seen = doc.get('seen', doc)
        if not isinstance(seen, dict):
            raise ValueError('El archivo de ofertas tiene un formato no válido.')
        jobs = [dict(v, key=k) for k, v in seen.items() if isinstance(v, dict)]
    sections, profile_version = profile_data()
    return {'fields': fields, 'applications': rows, 'version': version, 'jobs': jobs,
            'profile_sections': sections, 'profile_version': profile_version,
            'profile': PROFILE.read_text(encoding='utf-8') if PROFILE.exists() else '', 'token': TOKEN}


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, content_type):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path == '/':
                self.send(200, HTML.read_bytes(), 'text/html; charset=utf-8')
            elif self.path == '/profile-ui.js':
                self.send(200, HTML.with_name('profile-ui.js').read_bytes(), 'text/javascript; charset=utf-8')
            elif self.path == '/neobrutalism.css':
                self.send(200, HTML.with_name('neobrutalism.css').read_bytes(), 'text/css; charset=utf-8')
            elif self.path == '/api/data':
                self.send(200, json.dumps(load_data(), ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')
            else:
                self.send_error(404)
        except (ValueError, OSError) as e:
            self.send(500, json.dumps({'error': str(e)}).encode(), 'application/json')

    def do_POST(self):
        if self.path not in ('/api/application', '/api/profile') or self.headers.get('X-Dashboard-Token') != TOKEN:
            self.send_error(403)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 32768:
                raise ValueError('Tamaño de solicitud no válido.')
            data = json.loads(self.rfile.read(length))
            with WRITE_LOCK:
                if self.path == '/api/profile':
                    write_profile_section(data)
                else:
                    write_entry(data)
            self.send(200, b'{"ok":true}', 'application/json')
        except (ValueError, OSError, TypeError) as e:
            self.send(409 if isinstance(e, FileExistsError) else 400, json.dumps({'error': str(e)}).encode('utf-8'), 'application/json; charset=utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Panel local de búsqueda de empleo')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Panel disponible en http://127.0.0.1:{args.port}  (Ctrl+C para salir)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
