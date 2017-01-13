from flask import Flask, render_template
from flask_sslify import SSLify
from flask_heroku import Heroku
from flask_bootstrap import Bootstrap
import os

app = Flask(__name__)
heroku = Heroku(app)
print os.environ.get('ENV')
if os.environ.get('ENV') != 'dev':
    sslify = SSLify(app)

@app.route('/')
def http_parrots():

    return render_template('http_parrots.html', status_code_list=pruned_status_codes())

@app.route('/<status_code>')
def http_parrot():
    return render_template('http_parrot.html', status_code=status_code)

def pruned_status_codes():
    working_status_codes = []
    status_code_list = [["100","Continue"],["101","Switching Protocols"],["102","Processing"],["200","OK"],["201","Created"],["202","Accepted"],["203","Non-Authoritative Information"],["204","No Content"],["205","Reset Content"],["206","Partial Content"],["207","Multi-Status"],["208","Already Reported"],["226","IM Used"],["300","Multiple Choices"],["301","Moved Permanently"],["302","Found"],["303","See Other"],["304","Not Modified"],["305","Use Proxy"],["306","Switch Proxy"],["307","Temporary Redirect"],["308","Permanent Redirect"],["400","Bad Request"],["401","Unauthorized"],["402","Payment Required"],["403","Forbidden"],["404","Not Found"],["405","Method Not Allowed"],["406","Not Acceptable"],["407","Proxy Authentication Required"],["408","Request Time-out"],["409","Conflict"],["410","Gone"],["411","Length Required"],["412","Precondition Failed"],["413","Payload Too Large"],["414","URI Too Long"],["415","Unsupported Media Type"],["416","Range Not Satisfiable"],["417","Expectation Failed"],["418","I'm a teapot"],["421","Misdirected Request"],["422","Unprocessable Entity"],["423","Locked"],["424","Failed Dependency"],["426","Upgrade Required"],["428","Precondition Required"],["429","Too Many Requests"],["431","Request Header Fields Too Large"],["451","Unavailable For Legal Reasons"],["500","Internal Server Error"],["501","Not Implemented"],["502","Bad Gateway"],["503","Service Unavailable"],["504","Gateway Time-out"],["505","HTTP Version Not Supported"],["506","Variant Also Negotiates"],["507","Insufficient Storage"],["508","Loop Detected"],["510","Not Extended"],["511","Network Authentication Required"],["103","Checkpoint"],["103","Early Hints"],["419","I'm a fox"],["420","Enhance Your Calm"],["450","Blocked by Windows Parental Controls"],["498","Invalid Token"],["499","Token Required"],["499","Request has been forbidden by antivirus"],["509","Bandwidth Limit Exceeded"],["530","Site is frozen"]]
    for status_code in status_code_list:
        if os.path.exists(os.getcwd()+'/static/'+status_code[0]+'.jpg'):
            working_status_codes.append(status_code)
    return working_status_codes
