import base64
import os
import time
from contextlib import contextmanager
from threading import Thread

import pytest
import requests

from weavelib.exceptions import ObjectNotFound, BadArguments
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
        dashboard_rpc_info = find_rpc(self, "b", "static_files")
        self.http_client = RPCClient(self.get_connection(), dashboard_rpc_info,
                                     self.get_auth_token())

    def number(self, param):
        return param + 1

    def api(self, param):
        return "API" + param

    def exception(self):
        raise ObjectNotFound("blah")

    def on_service_start(self):
        self.rpc_server.start()
        self.http_client.start()

    def on_service_stop(self):
        self.http_client.stop()
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
        cls.service.service_stop()
        cls.dummy_service.service_stop()
        cls.conn.close()
        cls.messaging_service.service_stop()

    def test_bad_static_file(self):
        url = "http://localhost:15000/static/bad.html"
        response = requests.get(url)
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
        content = base64.b64encode(b"test").decode('ascii')
        rel_path = self.dummy_service.http_client["register"]("/a/x", content,
                                                              _block=True)

        url = "http://localhost:15000/static/" + rel_path

        response = requests.get(url)
        assert response.status_code == 200
        assert response.content == b"test"

    def test_unregister_directory(self):
        content = base64.b64encode(b"test").decode('ascii')
        rel_paths = [
            self.dummy_service.http_client["register"]("/b/" + str(x), content,
                                                       _block=True)
            for x in range(5)
        ]

        for rel_path in rel_paths:
            url = "http://localhost:15000/static/" + rel_path
            response = requests.get(url)
            assert response.status_code == 200

        self.dummy_service.http_client["unregister"]("/b/", _block=True)

        for rel_path in rel_paths:
            url = "http://localhost:15000/static/" + rel_path
            response = requests.get(url)
            assert response.status_code == 404

    def test_register_bad_path(self):
        content = base64.b64encode(b"test").decode('ascii')
        with pytest.raises(BadArguments):
            self.dummy_service.http_client["register"]("../../../../x", content,
                                                       _block=True)
