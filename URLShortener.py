from flask import Flask, request, redirect, render_template_string, url_for, flash
import sqlite3
from sqlite3 import Connection
import string, random, datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'change_this_in_prod')
DB_PATH = 'urls.db'


def get_conn() -> Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original TEXT NOT NULL,
            short TEXT NOT NULL UNIQUE,
            visits INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()



ALPHABET = string.ascii_letters + string.digits
SHORT_LEN = 6


def generate_code(length=SHORT_LEN):
    return ''.join(random.choices(ALPHABET, k=length))


def make_unique_code():
    conn = get_conn()
    c = conn.cursor()
    for _ in range(10_000):
        code = generate_code()
        c.execute('SELECT 1 FROM urls WHERE short = ?', (code,))
        if not c.fetchone():
            conn.close()
            return code
    conn.close()
    raise RuntimeError('unable to generate unique code')


INDEX_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>url shortener</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body class="bg-light">
    <div class="container py-5">
      <div class="card shadow-sm">
        <div class="card-body">
          <h1 class="card-title mb-3">url shortener — internship project</h1>
          <p class="text-muted">paste a long url, get a short link. uses sqlite db.</p>

          {% with messages = get_flashed_messages() %}
            {% if messages %}
              <div class="alert alert-warning">{{ messages[0] }}</div>
            {% endif %}
          {% endwith %}

          <form method="post" action="{{ url_for('create') }}">
            <div class="mb-3">
              <label for="original" class="form-label">long url</label>
              <input type="url" class="form-control" id="original" name="original" placeholder="https://example.com/long/path" required>
            </div>
            <div class="mb-3">
              <label for="custom" class="form-label">custom short code (optional)</label>
              <input type="text" class="form-control" id="custom" name="custom" placeholder="custom123 (a-zA-Z0-9, 3-20 chars)">
            </div>
            <button class="btn btn-primary">shorten</button>
          </form>

          {% if short_url %}
          <hr>
          <div>
            <p>short url:</p>
            <p><a href="{{ short_url }}" target="_blank">{{ short_url }}</a></p>
            <p class="small">stats: <a href="{{ stats_url }}">view</a></p>
          </div>
          {% endif %}

        </div>
      </div>

      <footer class="mt-4 text-muted small">made with ♥ — single-file demo. edit app.py to customize.</footer>
    </div>
  </body>
</html>
"""

STATS_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>stats for {{ short }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body class="p-4 bg-light">
    <div class="container">
      <div class="card">
        <div class="card-body">
          <h3>stats for <code>{{ short }}</code></h3>
          <p><strong>original:</strong> <a href="{{ original }}">{{ original }}</a></p>
          <p><strong>visits:</strong> {{ visits }}</p>
          <p><strong>created at:</strong> {{ created_at }}</p>
          <a href="{{ home }}" class="btn btn-sm btn-outline-primary mt-2">home</a>
        </div>
      </div>
    </div>
  </body>
</html>
"""

@app.route('/', methods=['GET'])
def index():
    return render_template_string(INDEX_HTML, short_url=None)


@app.route('/create', methods=['POST'])
def create():
    original = request.form.get('original', '').strip()
    custom = request.form.get('custom', '').strip()

    if not original:
        flash('please provide a valid url')
        return redirect(url_for('index'))
    if custom:
        if not (3 <= len(custom) <= 20) or any(c not in ALPHABET for c in custom):
            flash('custom code invalid — use 3-20 chars a-zA-Z0-9')
            return redirect(url_for('index'))

    conn = get_conn()
    c = conn.cursor()

    if custom:
        c.execute('SELECT 1 FROM urls WHERE short = ?', (custom,))
        if c.fetchone():
            flash('custom code already taken')
            conn.close()
            return redirect(url_for('index'))
        short = custom
    else:
        short = make_unique_code()

    now = datetime.datetime.utcnow().isoformat()
    try:
        c.execute('INSERT INTO urls (original, short, created_at) VALUES (?, ?, ?)', (original, short, now))
        conn.commit()
    except sqlite3.IntegrityError:
        flash('unexpected error — maybe short code collision, try again')
        conn.close()
        return redirect(url_for('index'))

    conn.close()
    short_url = request.url_root.rstrip('/') + '/' + short
    stats_url = url_for('stats', short=short)
    return render_template_string(INDEX_HTML, short_url=short_url, stats_url=stats_url)


@app.route('/<short>')
def redirect_short(short):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT original, visits FROM urls WHERE short = ?', (short,))
    row = c.fetchone()
    if not row:
        conn.close()
        return ("not found" , 404)
    original = row['original']
    visits = row['visits'] + 1
    c.execute('UPDATE urls SET visits = ? WHERE short = ?', (visits, short))
    conn.commit()
    conn.close()
    return redirect(original)


@app.route('/stats/<short>')
def stats(short):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT original, visits, created_at FROM urls WHERE short = ?', (short,))
    row = c.fetchone()
    conn.close()
    if not row:
        return ('not found', 404)
    return render_template_string(STATS_HTML, short=short, original=row['original'], visits=row['visits'], created_at=row['created_at'], home=url_for('index'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
