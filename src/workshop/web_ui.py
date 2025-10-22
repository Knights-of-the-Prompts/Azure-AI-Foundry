from flask import Flask, render_template, request, redirect, url_for, send_file, abort, jsonify
import os
import uuid
import io

app = Flask(__name__, static_folder='static', template_folder='templates')

# Simple in-memory report store for demo/downloads (id -> report dict)
REPORT_STORE = {}


def get_cm():
    """Lazily obtain a ComplianceManager instance.

    If the environment variable USE_DUMMY_CM is set (truthy), this returns
    a simple DummyCM that doesn't make external calls. Otherwise, it
    will attempt to construct the real ComplianceManager and fall back to
    DummyCM on any error. This avoids importing credentials/performing
    network calls at module import time.
    """
    use_dummy = os.environ.get('USE_DUMMY_CM')

    class DummyCM:
        CATEGORY_MAP = {
            'Data protection & Privacy': {'scope': 'Data protection', 'default_controls': 'N/A'},
            'Pharmaceutical regulations': {'scope': 'Pharmaceutical regulations', 'default_controls': 'N/A'},
            'ISO standards': {'scope': 'ISO standards', 'default_controls': 'N/A'},
            'Environmental & Sustainability regulations': {'scope': 'Environmental & Sustainability', 'default_controls': 'N/A'},
        }

        def __init__(self, require_citations=True):
            self.require_citations = require_citations

        def search_updates(self, scope, jurisdiction=None):
            return [{'title': f'Dummy update for {scope}', 'url': 'https://example.com/dummy'}]

        def handle_query(self, q):
            return [{'title': 'Dummy refined result', 'url': 'https://example.com/refined'}]

        def create_compliance_report(self, scope, controls_text, jurisdiction=None):
            return {'scope': scope, 'controls': controls_text, 'jurisdiction': jurisdiction, 'findings': [], 'summary': 'Dummy report'}

    if use_dummy and use_dummy not in ('0', 'false', 'False'):
        return DummyCM()

    try:
        # Import here to avoid import-time side effects
        from src.workshop.compliance_manager import ComplianceManager

        return ComplianceManager(require_citations=True)
    except Exception as exc:  # pragma: no cover - fallback for local dev
        # Fall back to DummyCM if real CM cannot be created (missing creds, network, etc.)
        print('Warning: could not create real ComplianceManager, using DummyCM fallback:', exc)
        return DummyCM()


@app.route('/', methods=['GET'])
def index():
    cm = get_cm()
    categories = list(cm.CATEGORY_MAP.keys())
    return render_template('compliance_manager/index.html', categories=categories)


@app.route('/search', methods=['POST'])
def search():
    cm = get_cm()
    category = request.form.get('category')
    scope = cm.CATEGORY_MAP.get(category, {}).get('scope')
    jurisdiction = request.form.get('jurisdiction') or None
    updates = cm.search_updates(scope, jurisdiction=jurisdiction)
    default_controls = cm.CATEGORY_MAP.get(category, {}).get('default_controls', '')
    return render_template('compliance_manager/result.html', category=category, updates=updates, jurisdiction=jurisdiction, default_controls=default_controls)


@app.route('/refine', methods=['POST'])
def refine():
    cm = get_cm()
    category = request.form.get('category')
    scope = cm.CATEGORY_MAP.get(category, {}).get('scope')
    refinement = request.form.get('refinement') or ''
    refined = cm.handle_query(f"Latest official updates on {scope}. {refinement}")
    default_controls = cm.CATEGORY_MAP.get(category, {}).get('default_controls', '')
    return render_template('compliance_manager/result.html', category=category, updates=refined, jurisdiction=None, default_controls=default_controls)


@app.route('/create_report', methods=['POST'])
def create_report():
    cm = get_cm()
    category = request.form.get('category')
    scope = cm.CATEGORY_MAP.get(category, {}).get('scope')
    jurisdiction = request.form.get('jurisdiction') or None
    controls_text = request.form.get('controls_text')
    if not controls_text:
        controls_text = cm.CATEGORY_MAP.get(category, {}).get('default_controls', '')

    # Generate the report (may take time)
    report = cm.create_compliance_report(scope=scope, controls_text=controls_text, jurisdiction=jurisdiction)

    # Store and generate id
    rid = str(uuid.uuid4())
    REPORT_STORE[rid] = report

    return render_template('compliance_manager/report.html', category=category, report=report, report_id=rid)


@app.route('/download_report/<rid>', methods=['GET'])
def download_report(rid):
    report = REPORT_STORE.get(rid)
    if not report:
        abort(404)
    # Return JSON as attachment
    import json
    data = json.dumps(report, indent=2)
    return send_file(io.BytesIO(data.encode('utf-8')), mimetype='application/json', as_attachment=True, download_name=f'compliance_report_{rid}.json')


@app.route('/confirm', methods=['POST'])
def confirm():
    # For now just show a confirmation page and allow user to request a report later via API
    category = request.form.get('category')
    return render_template('compliance_manager/confirm.html', category=category)


def run(host='127.0.0.1', port=5000, debug=False):
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    run(debug=True)
