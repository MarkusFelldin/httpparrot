import random
from flask import Flask, render_template, send_from_directory, abort, request, redirect, url_for
import os

app = Flask(__name__)


@app.route('/')
def http_parrots():
    return render_template('http_parrots.html', status_code_list=pruned_status_codes())


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
        code = 200
    image = find_image(status_code)
    if image and request.accept_mimetypes.best_match(['text/html', 'image/*']) == 'image/*':
        return send_from_directory('static', image), code
    description = next((s[1] for s in status_code_list if s[0] == status_code), '')
    return render_template('http_parrot.html', status_code=status_code,
                           description=description, image=image), code


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
    return working_status_codes
