'''
Julielib - Module WebPy, version 2.0
WebPy is a framework for making a prototype server with minimal changing
of code.

Cloned from: https://github.com/Sanjay-Ganeshan/WebPy

'''

import http.server
from http import HTTPStatus
import threading
import json
import pickle
import urllib.parse
import requests
import math

def get_function_argument_names(fn):
    ''' Gets the first few local variables in function scope, will always be args'''
    # Must use self as instance reference, or it'll get confused
    return [arg for arg in (list(fn.__code__.co_varnames)[:fn.__code__.co_argcount]) if arg != 'self']

def prune_dictionary_to_keys(d, keys):
    return {k:d[k] for k in keys if k in d}

def extract_args_and_kwargs(obj):
    if type(obj) is dict:
        if 'args' in obj or 'kwargs' in obj:
            args = obj.get('args',[])
            kwargs = obj.get('kwargs',{})
        else:
            args = []
            kwargs = obj
    elif type(obj) is list or type(obj) is tuple:
        # Assume a list is just args
        args = tuple(obj)
        kwargs = {}
    else:
        if getattr(obj,'args', None) is not None or getattr(obj,'kwargs', None) is not None:
           args = getattr(obj,'args',[])
           kwargs = getattr(obj, 'kwargs',{})
        else:
            args = [obj]
            kwargs = {}
    return args, kwargs

class WebPyServer(object):
    def __init__(self, hostname, port, function_provider, codec, thread_calls=False, new_object_per_call=False):
        self.hostname = hostname
        self.port = port
        self.lib = function_provider
        self.thread_requests = thread_calls
        self.instantiate_lib_for_call = new_object_per_call
        self.handler = self.create_handler()
        self.codec = codec
        assert callable(getattr(self.codec,'encode',None)) and callable(getattr(self.codec,'decode',None)), "Codec must have encode and decode method!"
        self._serverclass = http.server.ThreadedHTTPServer if self.thread_requests else http.server.HTTPServer
        self.server = self._serverclass((self.hostname, self.port), self.handler)
        self.is_running = False
        
    def start_server(self, new_thread=True):
        self.is_running = True
        def run_thread():
            self.server.serve_forever()
        if new_thread:
            thr = threading.Thread(target=run_thread,args=(),kwargs={})
            thr.daemon = True
            thr.start()
        else:
            run_thread()

    def stop_server(self):
        if self.is_running:
            self.server.shutdown()
        self.is_running = False
    def is_running(self):
        return self.is_running
    def handle_request(self, handler_ref, request_type):
        obj_of_interest = self.lib() if self.instantiate_lib_for_call else self.lib
        path = handler_ref.path
        is_allowed=True
        if hasattr(obj_of_interest,'get_allowed_webpy_paths'):
            if callable(obj_of_interest.get_allowed_webpy_paths):
                try:
                    allowed_paths = obj_of_interest.get_allowed_webpy_paths()
                except:
                    allowed_paths = None
                if allowed_paths is not None:
                    is_allowed = path in allowed_paths
        max_depth = None
        if hasattr(obj_of_interest,'get_allowed_webpy_depth'):
            if callable(obj_of_interest.get_allowed_webpy_depth):
                try:
                    max_depth = obj_of_interest.get_allowed_webpy_depth()
                except:
                    max_depth = None
                if max_depth is not None:
                    is_allowed = path.count('/') <= max_depth
        path_parts = path.split('/')[1:]
        if not is_allowed:
            handler_ref.send_response(HTTPStatus.UNAUTHORIZED)
            handler_ref.end_headers()
            handler_ref.wfile.write(self.codec.encode('The provided path %s is inaccessible on the server.' % path))
            handler_ref.wfile.flush()
            return
        path_invalid = False
        for part in path_parts:
            sub = getattr(obj_of_interest, part, None)
            if sub is None:
                path_invalid = True
                break
            else:
                obj_of_interest = sub
        if path_invalid:
            handler_ref.send_response(HTTPStatus.NOT_FOUND)
            handler_ref.end_headers()
            handler_ref.wfile.write(self.codec.encode('The provided path %s is invalid' % path))
            handler_ref.wfile.flush()
            return

        # We have this resource
        # First, determine if it's a function
        succeeded = False
        errormsg = ''
        if callable(obj_of_interest):
            # It's a function, let's parse for arguments
            arg_names = get_function_argument_names(obj_of_interest)
            fn_args, fn_kwargs = [], {}
            if len(arg_names) > 0:
                # If there are no arguments, throwing an exception is weird
                if request_type != 'GET':
                    content_length = int(handler_ref.headers['Content-Length'])
                    content_type = handler_ref.headers['Content-Type']
                    request_input = handler_ref.rfile.read(content_length)
                    request_input_obj = self.codec.decode(request_input)
                    fn_args, fn_kwargs = extract_args_and_kwargs(request_input_obj)
            response = None
            try:
                response = obj_of_interest(*fn_args, **fn_kwargs)
            except TypeError as err:
                # Not the correct number/type of arguments
                succeeded = False
                print(err)
                errormsg = '"Invalid arguments. Expecting %s"' % str(arg_names)
            except Exception as err:
                # Something else went wrong
                succeeded = False
                errormsg = '"Something went wrong when calling that function"'
                print(str(err))
            else:
                succeeded = True
        else:
            # It's just some constant value
            response = obj_of_interest
            succeeded = True
        if succeeded:
            response = self.codec.encode(response)
            handler_ref.send_response(HTTPStatus.OK)
            handler_ref.send_header('Content-Length', len(response))
            handler_ref.end_headers()
        else:
            response = self.codec.encode(errormsg)
            handler_ref.send_response(HTTPStatus.BAD_REQUEST)
            handler_ref.end_headers()
        handler_ref.wfile.write(response)
        handler_ref.wfile.flush()

    '''
        if request_type == 'GET':
            handler_ref.send_response(200)
            handler_ref.send_header("Content-type", "application/json")
            handler_ref.end_headers()
            handler_ref.wfile.flush()
    '''
    def create_handler(self):
        wpServer = self
        class WebPyInnerHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(inner_self):
                wpServer.handle_request(inner_self, 'GET')
            def do_POST(inner_self):
                wpServer.handle_request(inner_self, 'POST')
            def do_PUT(inner_self):
                wpServer.handle_request(inner_self, 'PUT')
            def do_DELETE(inner_self):
                wpServer.handle_request(inner_self, 'DELETE')
        return WebPyInnerHandler
    def make_client(self):
        return WebPyClient(self.hostname, self.port, self.codec)
    def __str__(self):
        return 'WebPyServer@%s:%d' % (self.hostname, self.port)
class WebPyJSONObject(object):
    def __init__(self, data):
        assert type(data) in [list,dict], 'WebpyJSON only supports standard JS'
        self.internal_webpy_data = data
        self.is_list = type(self.internal_webpy_data) is list
        self.is_dict = type(self.internal_webpy_data) is dict
        assert self.is_list or self.is_dict, 'Something impossible happened'
    def __getitem__(self, item):
        ret = self.internal_webpy_data.__getitem__(item)
        return WebPyJSONObject.wrap(ret)
    def __getattr__(self, attribute_name):
        return WebPyJSONObject.wrap(self.internal_webpy_data[attribute_name])
    def __str__(self):
        return str(self.internal_webpy_data)
    @staticmethod
    def wrap(data):
        # We can only wrap JSON supported objects
        if data is None or type(data) in [int, float, bool, str]:
            # primitive, just return it
            return data
        elif type(data) in [list, dict]:
            return WebPyJSONObject(data)
        else:
            raise TypeError('WebPyJSON can only be used on JSON objects, or will have undefined behaviour')

class WebPyJSONCodec(object):
    @staticmethod
    def encode(obj):
        return json.dumps(obj).encode()

    @staticmethod
    def decode(s):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return {}

class WebPyBinaryCodec(object):
    @staticmethod
    def encode(obj):
        return pickle.dumps(obj)

    @staticmethod
    def decode(s):
        return pickle.loads(s)

class WebPyClient(object):
    def __init__(self, hostname=None, port=None, codec=None, parentext=None):
        assert (parentext is not None) or (hostname is not None and port is not None and codec is not None)
        if parentext is not None:
            parent, ext = parentext
            self._hostname = parent._hostname
            self._port = parent._port
            self.basename = parent.basename
            self.codec = parent.codec
            self.desired_webpy_path = '%s/%s' % (parent.desired_webpy_path, ext)
        else:
            self.desired_webpy_path = ''
            self.codec = codec
            self.basename = 'http://%s:%d/' % (hostname, port)
            self._hostname = hostname
            self._port= port
    def __getattr__(self, attribute_name):
        assert not('/') in attribute_name, 'No using slashes!'
        return WebPyClient(parentext=(self,attribute_name))
    def unpack(self):
        response = requests.get(self._get_url())
        response = self.codec.decode(response.content)
        return response
        
    def _get_url(self):
        assert self._has_url(), 'Must have url to apply operation'
        return urllib.parse.urljoin(self.basename, self.desired_webpy_path)

    def _has_url(self):
        return len(self.desired_webpy_path) > 0

    def __call__(self, *args, **kwargs):
        response = requests.post(self._get_url(), self.codec.encode({'args':args, 'kwargs':kwargs}))
        if response.ok:
            response = self.codec.decode(response.content)
            return response
        else:
            raise IOError('Could not communicate with server! %s, %s' % (str(response), response.content))
    
    def __repr__(self):
        return "<Client: %s>" % self._hostname

    def __str__(self):
        if self._has_url():
            return str(self.unpack())
        else:
            return repr(self)
    
    '''
    Override every operator to maximize compatibility
    without using unpack()
    '''
    def __format__(self, format_spec):
        return self.unpack() % (format_spec)
    def __lt__(self, other):
        return self.unpack() < other
    def __gt__(self, other):
        return self.unpack() > other
    def __le__(self, other):
        return self.unpack() <= other
    def __ge__(self, other):
        return self.unpack() >= other
    def __eq__(self, other):
        return self.unpack() == other
    def __bool__(self):
        return bool(self.unpack())
    def __len__(self):
        return len(self.unpack())
    def __getitem__(self, ix):
        return self.unpack()[ix]
    def __iter__(self):
        return iter(self.unpack())
    def __reversed__(self):
        return reversed(self.unpack())
    def __contains__(self, o):
        return o in self.unpack()
    def __add__(self, o):
        return self.unpack() + o
    def __sub__(self, o):
        return self.unpack() - o
    def __mul__(self, o):
        return self.unpack() * o
    def __truediv__(self, o):
        return self.unpack() / o
    def __floordiv__(self, o):
        return self.unpack() // o
    def __mod__(self, other):
        return self.unpack() % other
    def __pow__(self, other, modulo=None):
        if modulo is not None:
            pow(self.unpack(), other, modulo)
        else:
            return self.unpack() ** other
    def __lshift__(self, o):
        return self.unpack() << o
    def __rshift__(self, o):
        return self.unpack() >> o
    def __and__(self, o):
        return self.unpack() & o
    def __xor__(self, o):
        return self.unpack() ^ o
    def __or__(self, o):
        return self.unpack() | o
    def __radd__(self, o):
        return o + self.unpack()
    def __rsub__(self, o):
        return o - self.unpack()
    def __rmul__(self, o):
        return o * self.unpack()
    def __rpow__(self, o):
        return o ** self.unpack()
    def __rlshift__(self, o):
        return o << self.unpack()
    def __rrshift__(self, o):
        return o >> self.unpack()
    def __rand__(self, o):
        return o & self.unpack()
    def __rxor__(self, o):
        return o ^ self.unpack()
    def __ror__(self, o):
        return o | self.unpack()
    def __neg__(self):
        return -self.unpack()
    def __pos__(self):
        return +self.unpack()
    def __abs__(self):
        return abs(self.unpack())
    def __invert__(self):
        return self.unpack().__invert__()
    def __complex__(self):
        return complex(self.unpack())
    def __int__(self):
        return int(self.unpack())
    def __float__(self):
        return float(self.unpack())
    def __index__(self):
        return self.unpack().__index__()
    def __round__(self, ndigits=None):
        if ndigits is not None:
            return round(self.unpack(), ndigits)
        else:
            return round(self.unpack())
    def __trunc__(self):
        return math.trunc(self.unpack())
    def __ceil__(self):
        return math.ceil(self.unpack())
    def __floor__(self):
        return math.floor(self.unpack())
        

def expose(lib, hostname='localhost', port=8080, codec=None):
    if codec is None:
        codec=WebPyBinaryCodec
    server = WebPyServer(hostname,port,lib, codec=codec)
    server.start_server()
    return server

def make_client(hostname='localhost',port=8080,codec=None):
    if codec is None:
        codec=WebPyBinaryCodec
    client = WebPyClient(hostname, port, codec)
    return client