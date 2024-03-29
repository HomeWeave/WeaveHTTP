import base64
import hashlib
import json
import logging
import os
import shutil
import tempfile
from collections import defaultdict
from threading import Lock
from uuid import uuid4

from bottle import response, static_file

from weavelib.exceptions import BadArguments
from weavelib.rpc import RPCClient, find_rpc
from weavelib.rpc import RPCServer, ServerAPI, ArgParameter, get_rpc_caller


logger = logging.getLogger(__name__)


def get_required_argument(obj, key):
    try:
        return obj[key]
    except KeyError:
        raise BadArguments(key)


def jsonify_response(code, result):
    response.status = code
    response.content_type = 'application/json'
    if int(code / 100) == 2:
        return json.dumps({"status": "ok", "data": result})
    elif int(code / 100) in (4, 5):
        return json.dumps({"status": "error", "message": result})
    return json.dumps(result)


class BaseHTTPModule(object):
    def transform_response(self, code, response):
        response.status = code
        if int(code / 100) == 2:
            return response
        elif int(code / 100) == 4:
            return "Client Error {}: {}".format(code, response)
        elif int(code / 100) == 5:
            return "Internal Error {}: {}".format(code, response)


class RPCModule(BaseHTTPModule):
    def __init__(self, service):
        self.service = service
        self.clients = {}
        self.clients_lock = Lock()

    def start(self):
        pass

    def stop(self):
        with self.clients_lock:
            for client in self.clients.values():
                client.stop()

    def get_registrations(self):
        return [("POST", "", self.handle_rpc)]

    def handle_rpc(self, body):
        app_url = get_required_argument(body, 'app_url')
        rpc_name = get_required_argument(body, 'rpc_name')
        api_name = get_required_argument(body, 'api_name')
        args = get_required_argument(body, 'args')

        with self.clients_lock:
            client = self.clients.get((app_url, rpc_name), None)

        if not client:
            rpc_info = find_rpc(self.service, app_url, rpc_name)

        with self.clients_lock:
            client = self.clients.get((app_url, rpc_name), None)
            if not client:
                client = RPCClient(self.service.get_connection(), rpc_info,
                                   self.service.get_auth_token())
                client.start()
                self.clients[(app_url, rpc_name)] = client

        response = client[api_name](*args, _block=True)

        return response

    def transform_response(self, code, response):
        return jsonify_response(code, response)


class StaticFileModule(BaseHTTPModule):
    def __init__(self, service):
        self.base_dir = tempfile.mkdtemp()
        self.rpc = RPCServer("static_files", "HTTP Registry", [
            ServerAPI("register", "Register a resource.", [
                ArgParameter("filename", "File name.", str),
                ArgParameter("content", "Base64 content", str),
            ], self.register),
            ServerAPI("unregister", "Unregister a resource", [
                ArgParameter("filename", "File name", str)
            ], self.unregister),
        ], service)
        self.pseudo_app_id_map = defaultdict(lambda: str(uuid4()))
        self.pseudo_app_id_map_lock = Lock()


    def start(self):
        logger.info("Using base dir for HTTP: %s", self.base_dir)
        self.rpc.start()

    def stop(self):
        self.rpc.stop()
        shutil.rmtree(self.base_dir)

    def get_registrations(self):
        return [
            ("GET", "/", lambda x: self.handle_static(x, "/index.html")),
            ("GET", "<path:path>", self.handle_static),
        ]

    def url_to_app_id(self, app_url):
        return hashlib.md5(app_url.encode('utf-8')).hexdigest()

    def register(self, filename, content):
        decoded = base64.b64decode(content)
        app_info = get_rpc_caller()
        app_id = self.url_to_app_id(app_info["app_url"])

        pseudo_id = self.get_pseudo_app_id(app_id)
        rel_path = os.path.join("apps", pseudo_id, filename.lstrip('/'))
        full_path = self.get_absolute_path(rel_path, filename)
        self.write_file(full_path, decoded)
        return rel_path

    def unregister(self, filename):
        app_info = get_rpc_caller()
        app_id = self.url_to_app_id(app_info["app_url"])
        pseudo_id = self.get_pseudo_app_id(app_id)
        rel_path = os.path.join("apps", pseudo_id, filename.lstrip('/'))
        full_path = self.get_absolute_path(rel_path, filename)
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        elif os.path.isfile(full_path):
            os.unlink(full_path)

    def write_file(self, full_path, content):
        try:
            os.makedirs(os.path.dirname(full_path))
        except:
            pass

        with open(full_path, "wb") as out:
            out.write(content)

    def get_absolute_path(self, rel_path, filename):
        full_path = os.path.join(self.base_dir, rel_path)
        norm_path = os.path.normpath(full_path)
        if norm_path.startswith(self.base_dir):
            return norm_path
        raise BadArguments(filename)

    def handle_static(self, params, path):
        return static_file(path, root=os.path.join(self.base_dir))

    def transform_response(self, code, result):
        return result

    def get_pseudo_app_id(self, app_id):
        with self.pseudo_app_id_map_lock:
            return self.pseudo_app_id_map[app_id]
