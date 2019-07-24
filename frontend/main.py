from flask import Flask, render_template, request
from flask_paginate import Pagination, get_page_args
import requests as req
import os
import json
import socket
from opentracing_instrumentation.client_hooks import install_all_patches
from jaeger_client import Config
from flask_opentracing import FlaskTracing
import logging

app = Flask(__name__)
host_name = host_name = socket.gethostname()
port = os.getenv('PORT', '80')
reg_timeout = float(os.getenv('TIMEOUT_REG', '5'))
other_timeout = float(os.getenv('TIMEOUT_OTHER', '5'))
app_server_hostname = os.getenv('PLANESPOTTER_API_ENDPOINT', 'localhost')
jaeger_host = os.getenv('JAEGER_HOST', 'localhost')
registry_url = 'http://{}/api/planes'.format(app_server_hostname)
planetypes_url = 'http://{}/api/planetypes'.format(app_server_hostname)
planedetails_url = 'http://{}/api/planedetails'.format(app_server_hostname)
planepicture_url = 'http://{}/api/planepicture'.format(app_server_hostname)
health_url = 'http://{}/api/healthcheck'.format(app_server_hostname)


@app.route('/')
@app.route('/index.html')
def index():
    return render_template('index.html', host_name=host_name, host_ip=host_ip)


@app.route('/registry.html')
def registry():
    page, per_page, offset = get_page_args()

    req_params = {'page': page}

    search_owner = request.args.get('owner', None)
    search_reg = request.args.get('reg', None)
    search_model = request.args.get('model', None)
    search_mfr = request.args.get('mfr', None)
    search_icao = request.args.get('icao', None)

    req_filters = []
    if search_owner:
        search_owner = '%{}%'.format(search_owner)
        req_filters.append({"name": "name", "op": "like", "val": search_owner})
    if search_reg:
        req_filters.append({"name": "n_number", "op": "eq",
                            "val": search_reg})
    if search_icao:
        req_filters.append({"name": "mode_s_code_hex", "op": "eq",
                            "val": search_icao})
    if search_model:
        search_model = '%{}%'.format(search_model)
        planedetails_model_fiter = {"name": "model", "op": "like",
                                    "val": search_model}
        req_filters.append({"name": "planedetails", "op": "has",
                            "val": planedetails_model_fiter})
    if search_mfr:
        search_mfr = '%{}%'.format(search_mfr)
        planedetails_mfr_fiter = {"name": "mfr", "op": "like",
                                  "val": search_mfr}
        req_filters.append({"name": "planedetails", "op": "has",
                            "val": planedetails_mfr_fiter})

    if search_owner or search_reg or search_model or search_mfr or search_icao:
        req_params['q'] = json.dumps(dict(filters=req_filters))

    headers = {'Content-Type': 'application/json'}
    try:
        resp = req.get(registry_url, params=req_params, headers=headers,
                       timeout=reg_timeout).json()
    except (req.exceptions.ConnectionError, req.exceptions.ReadTimeout):
        return render_template('500.html',
                               host_name=host_name, host_ip=host_ip), 500

    acfts_raw = resp.get('objects', None)

    acfts = [trim_dict_content(acft_raw) for acft_raw in acfts_raw]
    num_results = resp.get('num_results', 1)
    pagination = Pagination(page=page, total=num_results,
                            record_name='Aircrafts', bs_version=3)

    return render_template('registry.html', acfts=acfts, pagination=pagination,
                           host_name=host_name, host_ip=host_ip)


@app.route('/details.html')
def details():
    search_icoa = request.args.get('icao', None)
    search_reg = request.args.get('reg', None)
    req_headers = {'Content-Type': 'application/json'}

    if not search_icoa or search_icoa == '':
        if search_reg and search_reg != '':
            req_filters = [{"name": "n_number", "op": "eq", "val": search_reg}]
            req_params = {}
            req_params['q'] = json.dumps(dict(filters=req_filters))
            try:
                resp = req.get(registry_url, params=req_params,
                               headers=req_headers, timeout=reg_timeout)
                if resp.status_code == 500:
                    return render_template('500.html',
                                           host_name=host_name,
                                           host_ip=host_ip), 500
                resp_body = resp.json()
            except (req.exceptions.ConnectionError,
                    req.exceptions.ReadTimeout):
                return render_template('500.html', host_name=host_name,
                                       host_ip=host_ip), 500

            acfts_raw = resp_body.get('objects', None)
            if acfts_raw:
                acft = trim_dict_content(acfts_raw[0])
                icao = acft.get('mode_s_code_hex', None)
            else:
                return render_template('details.html', search=False,
                                       not_found=True,
                                       registration_id=search_reg,
                                       host_name=host_name, host_ip=host_ip)
        else:
            return render_template('details.html', search=False,
                                   host_name=host_name, host_ip=host_ip)
    else:
        req_filters = [{"name": "mode_s_code_hex", "op": "eq",
                        "val": search_icoa}]
        req_params = {}
        req_params['q'] = json.dumps(dict(filters=req_filters))
        try:
            resp = req.get(registry_url, params=req_params,
                           headers=req_headers, timeout=reg_timeout).json()
        except (req.exceptions.ConnectionError, req.exceptions.ReadTimeout):
            return render_template('500.html',
                                   host_name=host_name, host_ip=host_ip), 500

        acfts_raw = resp.get('objects', None)
        if acfts_raw:
            acft = trim_dict_content(acfts_raw[0])
        else:
            acft = None
        icao = search_icoa

    plane_details = None

    resp = req.get('{}/{}'.format(planepicture_url, icao),
                   timeout=other_timeout)

    if resp.status_code == 200:
        plane_picture = resp.json()
    elif resp.status_code == 500:
        return render_template('500.html',
                               host_name=host_name, host_ip=host_ip), 500
    else:
        plane_picture = None

    return render_template('details.html', acft=acft, picture=plane_picture,
                           acft_details=plane_details, icao=icao, search=True,
                           host_name=host_name, host_ip=host_ip)


@app.route('/health.html')
def health():
    app_server = None
    db_connection = None
    position_server = None
    picture_server = None
    redis_server = None
    try:
        resp = req.get(health_url, timeout=60)
        if resp.status_code == 200:
            health_detail = resp.json()
            db_connection = health_detail.get('database_connection', None)
            position_server = health_detail.get('position_data', None)
            picture_server = health_detail.get('picture_data', None)
            redis_server = health_detail.get('redis_server', None)
            app_server = True
    except (req.exceptions.ConnectionError, req.exceptions.ReadTimeout):
        pass

    return render_template('health.html', app_server=app_server,
                           db_connection=db_connection,
                           position_server=position_server,
                           picture_server=picture_server,
                           redis_server=redis_server,
                           host_name=host_name, host_ip=host_ip)


@app.route('/contact.html')
def contact():
    return render_template('contact.html',
                           host_name=host_name, host_ip=host_ip)


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html',
                           host_name=host_name, host_ip=host_ip), 500


def trim_dict_content(dict_to_trim):
    new_dict = {}
    for key, value in dict_to_trim.items():
        if isinstance(value, str):
            trimmed = value.strip()
            new_dict[key] = trimmed
        elif isinstance(value, dict):
            new_sub_dict = {}
            for sub_key, sub_value in value.items():
                trimmed = sub_value.strip()
                new_sub_dict[sub_key] = trimmed
            new_dict[key] = new_sub_dict
        elif isinstance(value, bool):
            new_dict[key] = value
    return new_dict


def get_ip():
    try:
        host_ip = socket.gethostbyname(host_name)
        print("IP : ", host_ip)
        return host_ip
    except:
        print("Unable to get Hostname and IP")


host_ip = get_ip()

if __name__ == '__main__':
    debugmode = os.getenv('DEBUG_MODE', False)

    log_level = logging.DEBUG
    logging.getLogger('').handlers = []
    logging.basicConfig(format='%(asctime)s %(message)s', level=log_level)

    # Create configuration object with enabled logging and sampling of all requests.
    config = Config(config={'sampler': {'type': 'const', 'param': 1},
                            'logging': True,
                            'local_agent':
                            # Also, provide a hostname of Jaeger instance to send traces to.
                                {'reporting_host': jaeger_host}},
                    # Service name can be arbitrary string describing this particular web service.
                    service_name="markf_vmworld_frontend")
    jaeger_tracer = config.initialize_tracer()
    tracing = FlaskTracing(jaeger_tracer, trace_all_requests=True, app = app)
    install_all_patches()

    app.run(host='0.0.0.0', debug=bool(debugmode), port=int(port))
