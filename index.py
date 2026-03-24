import random
from datetime import date
from flask import Flask, render_template, send_from_directory, abort, request, redirect, url_for, jsonify
import os
from status_descriptions import STATUS_INFO
from status_extra import STATUS_EXTRA

app = Flask(__name__)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.route('/')
def http_parrots():
    codes = pruned_status_codes()
    day_index = date.today().toordinal() % len(codes)
    featured = codes[day_index][0]
    return render_template('http_parrots.html', status_code_list=codes, featured=featured)


@app.route('/quiz')
def quiz():
    codes = pruned_status_codes()
    quiz_data = [{"code": c[0], "name": c[1], "image": c[2]} for c in codes]
    return render_template('quiz.html', quiz_data=quiz_data)


@app.route('/api-docs')
def api_docs():
    return render_template('api_docs.html')


@app.route('/flowchart')
def flowchart():
    return render_template('flowchart.html')


@app.route('/tester')
def tester():
    return render_template('tester.html')


@app.route('/api/check-url')
def check_url():
    import requests as req
    url = request.args.get('url', '')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    try:
        resp = req.head(url, allow_redirects=False, timeout=10)
        return jsonify({"code": resp.status_code, "url": url})
    except req.RequestException as e:
        return jsonify({"error": str(e)}), 502


@app.route('/random')
def random_parrot():
    codes = pruned_status_codes()
    choice = random.choice(codes)
    return redirect(url_for('http_parrot', status_code=choice[0]))


@app.route('/<status_code>')
def http_parrot(status_code):
    try:
        code = int(status_code)
    except ValueError:
        abort(404)
    if not any(s[0] == status_code for s in status_code_list):
        abort(404)
    # Only return the actual status code for 2xx/4xx/5xx.
    # 1xx and 3xx codes have special HTTP semantics that break the response.
    if code < 200 or 300 <= code < 400:
        code = 200
    image = find_image(status_code)
    best = request.accept_mimetypes.best_match(['text/html', 'image/*', 'application/json'])
    if image and best == 'image/*':
        return send_from_directory('static', image), code
    description = next((s[1] for s in status_code_list if s[0] == status_code), '')
    info = STATUS_INFO.get(status_code, {})
    extra = STATUS_EXTRA.get(status_code, {})
    if best == 'application/json':
        return jsonify({
            "code": status_code,
            "description": description,
            "image": f"/{image}" if image else None,
            "meaning": info.get("description", ""),
            "history": info.get("history", ""),
        }), code
    codes = pruned_status_codes()
    code_list = [c[0] for c in codes]
    try:
        idx = code_list.index(status_code)
    except ValueError:
        idx = -1
    prev_code = code_list[idx - 1] if idx > 0 else None
    next_code = code_list[idx + 1] if 0 <= idx < len(code_list) - 1 else None
    return render_template('http_parrot.html', status_code=status_code,
                           description=description, image=image, info=info,
                           extra=extra, prev_code=prev_code,
                           next_code=next_code), code


@app.route('/<status_code>.jpg')
def http_parrot_image(status_code):
    image = find_image(status_code)
    if not image:
        abort(404)
    return send_from_directory('static', image)


# Support code for setting correct codes and descriptions
status_code_list = [
    ["100", "Continue"], ["101", "Switching Protocols"], ["102", "Processing"],
    ["103", "Early Hints"],
    ["200", "OK"], ["201", "Created"], ["202", "Accepted"],
    ["203", "Non-Authoritative Information"], ["204", "No Content"],
    ["205", "Reset Content"], ["206", "Partial Content"],
    ["207", "Multi-Status"], ["208", "Already Reported"], ["226", "IM Used"],
    ["300", "Multiple Choices"], ["301", "Moved Permanently"], ["302", "Found"],
    ["303", "See Other"], ["304", "Not Modified"], ["305", "Use Proxy"],
    ["306", "Switch Proxy"], ["307", "Temporary Redirect"],
    ["308", "Permanent Redirect"],
    ["400", "Bad Request"], ["401", "Unauthorized"], ["402", "Payment Required"],
    ["403", "Forbidden"], ["404", "Not Found"], ["405", "Method Not Allowed"],
    ["406", "Not Acceptable"], ["407", "Proxy Authentication Required"],
    ["408", "Request Time-out"], ["409", "Conflict"], ["410", "Gone"],
    ["411", "Length Required"], ["412", "Precondition Failed"],
    ["413", "Payload Too Large"], ["414", "URI Too Long"],
    ["415", "Unsupported Media Type"], ["416", "Range Not Satisfiable"],
    ["417", "Expectation Failed"], ["418", "I'm a teapot"],
    ["419", "I'm a Fox"], ["420", "Enhance Your Calm"],
    ["421", "Misdirected Request"], ["422", "Unprocessable Entity"],
    ["423", "Locked"], ["424", "Failed Dependency"], ["425", "Too Early"],
    ["426", "Upgrade Required"], ["428", "Precondition Required"],
    ["429", "Too Many Requests"], ["431", "Request Header Fields Too Large"],
    ["444", "No Response"], ["450", "Blocked by Windows Parental Controls"],
    ["451", "Unavailable For Legal Reasons"],
    ["494", "Request Header Too Large"],
    ["498", "Invalid Token"], ["499", "Token Required"],
    ["500", "Internal Server Error"], ["501", "Not Implemented"],
    ["502", "Bad Gateway"], ["503", "Service Unavailable"],
    ["504", "Gateway Time-out"], ["505", "HTTP Version Not Supported"],
    ["506", "Variant Also Negotiates"], ["507", "Insufficient Storage"],
    ["508", "Loop Detected"], ["509", "Bandwidth Limit Exceeded"],
    ["510", "Not Extended"], ["511", "Network Authentication Required"],
    ["530", "Site is Frozen"],
]


IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.JPG', '.png', '.gif']


def find_image(code):
    for ext in IMAGE_EXTENSIONS:
        path = os.path.join('static', code + ext)
        if os.path.exists(path):
            return code + ext
    return None


def pruned_status_codes():
    working_status_codes = []
    for status_code in status_code_list:
        image = find_image(status_code[0])
        if image:
            working_status_codes.append(status_code + [image])
    working_status_codes.sort(key=lambda s: int(s[0]))
    return working_status_codes
