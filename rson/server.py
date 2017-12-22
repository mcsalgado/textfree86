import threading
import types
import socket
import traceback
import sys

from collections import OrderedDict

from wsgiref.simple_server import make_server, WSGIRequestHandler

from werkzeug.utils import redirect as Redirect
from werkzeug.wrappers import Request, Response
from werkzeug.exceptions import HTTPException, NotFound, BadRequest, NotImplemented, MethodNotAllowed

from . import format, objects

# make_form/make_link

class RequestHandler:
    def __init__(self, url, function):
        self.fn = function
        self.url = url

    def GET(self, path):
        return self.fn

    def POST(self, path, data):
        return self.fn(**data)

    def link(self):
        return objects.Form(self.url)



def handler_for(name, obj):
    return RequestHandler(name, obj)

class Router:
    def __init__(self):
        self.handlers = OrderedDict()
        self.paths = OrderedDict()
        self.service = None

    def add(self, name=None):
        def _add(obj):
            n = obj.__name__ if name is None else name
            self.handlers[n] = handler_for(n,obj)
            self.paths[obj]=n
            self.service = None
            return obj
        return _add

    def index(self):
        if self.service is None:
            attrs = OrderedDict()
            for name,o in self.handlers.items():
                attrs[name] = o.link()
            self.service = objects.Service(attrs)
        return self.service

    def handle(self, request):
        path = request.path[:]
        if path == '' or path == '/':
            out = self.index()
        else:
            path = path[1:].split('/',1)
            name = path[0]
            if name in self.handlers:
                args = format.parse(request.data.decode('utf-8'))
                out = self.handlers[name].POST(path, args)
        
        def transform(o):
            if isinstance(o, types.FunctionType) and o in self.paths:
                return self.handlers[self.paths[o]].link()
            return o

        return Response(format.dump(out, transform))

    def app(self):
        return WSGIApp(self.handle)

class WSGIApp:
    def __init__(self, handler):
        self.handler = handler

    def __call__(self, environ, start_response):
        request = Request(environ)
        try:
            response = self.handler(request)
        except (StopIteration, GeneratorExit, SystemExit, KeyboardInterrupt):
            raise
        except HTTPException as r:
            response = r
            self.log_error(r, traceback.format_exc())
        except Exception as e:
            trace = traceback.format_exc()
            self.log_error(e, trace)
            response = self.error_response(e, trace)
        return response(environ, start_response)

    def log_error(self, exception, trace):
        print(trace, file=sys.stderr)

    def error_response(self, exception, trace):
        return Response(trace, status='500 not ok (%s)'%exception)

class QuietWSGIRequestHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        pass

class Server(threading.Thread):
    def __init__(self, app, host="", port=0, request_handler=QuietWSGIRequestHandler):
        threading.Thread.__init__(self)
        self.daemon=True
        self.running = True
        self.server = make_server(host, port, app,
            handler_class=request_handler)

    @property
    def url(self):
        return u'http://%s:%d/'%(self.server.server_name, self.server.server_port)

    def run(self):
        self.running = True
        while self.running:
            self.server.handle_request()

    def stop(self):
        self.running =False
        if self.server and self.is_alive():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect(self.server.socket.getsockname()[:2])
                s.send(b'\r\n')
                s.close()
            except IOError:
                import traceback
                traceback.print_exc()
        self.join(5)
