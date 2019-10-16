import base64
import os
import time
from contextlib import contextmanager
from threading import Thread

import requests

from weavelib.exceptions import ObjectNotFound
from weavelib.messaging import WeaveConnection
from weavelib.rpc import find_rpc, ServerAPI, ArgParameter, RPCClient, RPCServer
from weavelib.services import BackgroundThreadServiceStart, MessagingEnabled
from weavelib.services import BaseService

from weavehttp.service import WeaveHTTPService

from test_utils import MessagingService, DummyEnvService


MESSAGING_PLUGIN_URL = "https://github.com/HomeWeave/WeaveServer.git"


class ThreadedWeaveHTTPService(BackgroundThreadServiceStart, WeaveHTTPService):
    pass


class DummyService(MessagingEnabled, BaseService):
    def __init__(self, conn, token):
        super(DummyService, self).__init__(auth_token=token, conn=conn)
        apis = [
            ServerAPI("api", "desc1", [
                ArgParameter("param", "d1", str),
            ], self.api),
            ServerAPI("number", "desc1", [
                ArgParameter("param", "d1", int),
            ], self.number),
            ServerAPI("exception", "desc1", [], self.exception),
        ]
        self.rpc_server = RPCServer("name", "desc", apis, self)

    def number(self, param):
        return param + 1

    def api(self, param):
        return "API" + param

    def exception(self):
        raise ObjectNotFound("blah")

    def on_service_start(self):
        dashboard_rpc_info = find_rpc(self, "b", "static_files")
        client = RPCClient(self.get_connection(), dashboard_rpc_info,
                           self.get_auth_token())
        client.start()

        content = base64.b64encode(b"test").decode('ascii')
        self.static_resource = client["register"]("/a/x", content, _block=True)

        client.stop()
        self.rpc_server.start()

    def on_service_stop(self):
        self.rpc_server.stop()


class TestWeaveHTTPService(object):
    @classmethod
    def setup_class(cls):
        cls.messaging_service = MessagingService()
        cls.messaging_service.service_start()
        cls.messaging_service.wait_for_start(15)

        cls.conn = WeaveConnection.local()
        cls.conn.connect()

        cls.env_service = DummyEnvService(cls.messaging_service.test_token,
                                          cls.conn)

        rpc_info = find_rpc(cls.env_service, MESSAGING_PLUGIN_URL,
                            "app_manager")
        appmgr_client = RPCClient(cls.env_service.get_connection(), rpc_info,
                                  cls.env_service.get_auth_token())
        appmgr_client.start()

        # Register the DummyService used in the test cases.
        test_token = appmgr_client["register_plugin"]("a", "b", _block=True)

        dummy_token = appmgr_client["register_plugin"]("x", "y", _block=True)

        appmgr_client.stop()

        cls.service = ThreadedWeaveHTTPService(auth_token=test_token,
                                               plugin_dir="x", venv_dir="y",
                                               conn=cls.conn, started_token="t")
        cls.service.service_start()
        cls.service.wait_for_start(15)

        cls.dummy_service = DummyService(cls.conn, dummy_token)
        cls.dummy_service.service_start()
        cls.dummy_service.wait_for_start(15)

    @classmethod
    def teardown_class(cls):
        cls.conn.close()
        cls.service.service_stop()
        cls.dummy_service.service_stop()
        cls.messaging_service.service_stop()

    def test_static_files(self):
        url = "http://localhost:15000/static/index.html"
        response = requests.get(url)
        assert response.status_code == 200

    def test_static_root(self):
        url = "http://localhost:15000/"
        response1 = requests.get(url)

        url = "http://localhost:15000/static/index.html"
        response2 = requests.get(url)

        assert response1.status_code == 200
        assert response1.text == response2.text

    def test_bad_static_file(self):
        url = "http://localhost:15000/static/bad.html"
        response = requests.get(url)
        print(response.text)
        assert response.status_code == 404

    def test_rpc(self):
        url = "http://localhost:15000/rpc/"
        data = {
            "app_url": "y",
            "rpc_name": "name",
            "api_name": "api",
            "args": ["test"],
        }
        response = requests.post(url, json=data)
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "data": "APItest"}

    def test_rpc_api_bad_arguments(self):
        url = "http://localhost:15000/rpc/"
        data = {
            "app_url": "y",
            "rpc_name": "name",
            "api_name": "number",
            "args": ["test"],
        }
        response = requests.post(url, json=data)
        assert response.status_code == 400
        assert response.json()["status"] == "error"
        assert "BadArguments" in response.json()["message"]

    def test_rpc_server_exception(self):
        url = "http://localhost:15000/rpc/"
        data = {
            "app_url": "y",
            "rpc_name": "name",
            "api_name": "exception",
            "args": [],
        }
        response = requests.post(url, json=data)
        assert response.status_code == 400
        assert response.json()["status"] == "error"
        assert "ObjectNotFound" in response.json()["message"]

    def test_plugin_static_resources(self):
        rel_path = self.dummy_service.static_resource
        url = "http://localhost:15000/static/" + rel_path

        response = requests.get(url)
        assert response.status_code == 200
        assert response.content == b"test"
