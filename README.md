django-rpcenable
================

Simple module to enable exposing functions over XML-RPC.

Overview
================

At it's core, django-rpcenable provides an XMLRPC entry point, along with a decorator that would allow you to expose your functions via XMLRPC and optionally log the calls made to them (and access the logs via the admin).

There are a few other features that you may choose to take advantage of:
 - Asynchronous (threaded) execution of calls - the response is returned right away while a separate thread runs the functtion
 - Stateless authentication with a pluggable "API User" model
 - Making outgoing XMLRPC requests with logging

Installation
===============
Put the 'rpcenable' folder on your PYTHONPATH. Add 'rpcenable' to the INSTALLED_APPS list. Run 'manage.py syncdb' to install the necessary tables.

Exposing functions via XMLRPC
===============
To enable XMLRPC exposure of a function of yours, you need to:
 1. Add urls.py entries where you want to expose the XMLRPC functions:

```python
(r'^rpc/$', rpcregistry.view),
(r'^rpc/v(?P<prefix>\d+)/$', rpcregistry.view) # Add this line if you want to enable version prefix
```

 2. Decorate your fuction with the "@rpcregistry.register_rpc" decorator:

```python
from rpcenable.registry import rpcregistry

@rpcregistry.register_rpc
def echo (var = ''):
    """
    Accepts an optional argument, which is appended to the string "Server says: "
    """
    return 'Server says: %s' % var
```

If you have RPCENABLE_LOG_INCOMING set to True in your settings.py, then you will be able to see a log with all past calls:
![Incoming Log](https://github.com/mtrdesign/django-rpcenable/raw/master/docimages/IncomingList.png)

Built-in authentication - theory
================
While you are free to implement a completely custom authentication, django-rpcenable comes bundled with a ready-to-use, stateless authentication mechanism.

The built-in authentication relies a on having the clocks between the authenticated parries synchronized to a certain degree (+- 5 minutes by default).

The authentication also relies on having a configured Django Cache backend, which supports reliable expiration of cache objects. It is highly recommended to use Memcached for that purpose.

To be able to before the server, the client must:
 0. Know its own username and API Key (a shared secret between the client and the server)
 1. Generate a completely random string, called nonce. Minimal length: 16 characters by default
 2. Get the current timestamp (Unix time, integer)
 3. Generate a SHA-256 HMAC of its API key along with  '%s;%s;%s' % (nonce, timestamp, username)
 4. Send over the 4 arguments (nonce, timestamp, username, signature) as the first argumens to the authenticated function

The above scheme allows for secure, stateless authentication between the client and the server.

Built-in authentication - practice
==================

You first need to decide whether you would use the built-in APIUser class, or if you would like to use your own model that would represent the API Users.

If it is the latter case, you would not need to make any changes. If you would want to have your own model, then you will need to:
 1. Have that model inherit 'rpcenable.abstractmodels.BaseAPIUser':

```python
from rpcenable.abstractmodels import BaseAPIUser

class MyAPIUser(BaseAPIUser):
    ...
```
 2. Add a ModelAdmin instance for this model to admin.py. If there are no significat (field) changes, you could use the built-in ModelAdmin:
```python
from rpcenable.abstractmodels import APIUserAdmin
admin.site.register (MyAPIUser, APIUserAdmin)
```
 3. Add the Python Path to your model in settings.py:
```python
RPCENABLE_USER_MODEL = 'mycustomapp.models.MyAPIUser' # Model to hook up the rpcenable.auth to
```

Once this is done, you can use the @rpcauth decorator to add authentication to your XMLRPC-exposed functions. Authenticated functions will automatically receive instance of the APIUser model as a first argument:
```python
@rpcregistry.register_rpc
@rpcauth
def auth_echo (user, var = ''):
    """
    Returns the + operation of the supplied argument.
    """
    return 'User %s says: %s' % (user,var)
```

![APIUser List](https://github.com/mtrdesign/django-rpcenable/raw/master/docimages/APIUserList.png)

Run functions in the background
================
It is often desirable to have an API return a result right away, while having another thread do the heavy lifting in the background. Django-rpcenable comes with a
helper decorator that allows you to do just that:

```python
from rpcenable.async import postpone

@postpone
def do_heavy_call(some_arg):
    # do the heavy work here...

@rpcregistry.register_rpc
def heavy_call (input_arg):
    my_heavy_call (input_arg)   # This part returns immediately after the jobs is pushed to a separate thread
    return "Heavy call scheduled."
```

If anything goes wrong while doing the heavy work, an email will be sent to the site administrators

Make external XMLRPC calls
================
Python comes fully equipped with an XMLRPC library that allows you to make external requests. Django-rpcenable builds on this functionality by adding:
 1. DB logging/Admin interface for the requests generated by the application
 2. Ability to easily use the same authentication scheme that is used for incoming calls

To use the outgoing XMLRPC requests, you will simply need to create an XMLRPC point.
```python
from rpcenable.registry import XMLRPCPoint

rpc = XMLRPCPoint('http://url.of.remote.rpc.service/')
rpc.echo ('Hi!') # this will call the 'echo' method on the remote service
```

To enable seamless authentication, the XMLRPCPoint constructor accepts an optional param_hook function. You could hook them together like this:
```python
from rpcenable.registry import XMLRPCPoint
from rpcenable.auth import generate_auth_args

# Param hook function to prepend the authentication arguments to a XMLRPC call
param_hook = lambda x: generate_auth_args('MY_APIUSER', 'MY_APIKEY') + x
# Shortcut for creating a usabel, authenticated XMLRPCPoint
get_rpcpoint = lambda : XMLRPCPoint('http://url.of.remote.rpc.service/', param_hook=param_hook)

authrpc = get_rpcpoint()
authrpc.echo ('Hi!') # this will call the 'echo' method on the remote service, with prepended authentication params/signature
```

Outgoing calls will only be logged if you have RPCENABLE_LOG_OUTGOING set to True in your settings.py:
![Outgoing calls](https://github.com/mtrdesign/django-rpcenable/raw/master/docimages/OutgoingList.png)


List of possible settings.py keys
================
```python
# RPCEnable Settings
RPCENABLE_USER_MODEL = 'mycustomapp.models.APIUser' # Model to hook up the rpcenable.auth to
RPCENABLE_LOG_INCOMING = True   # Whether to log incoming RPC requests to the database
RPCENABLE_LOG_OUTGOING = True   # Whether to log Outgoing RPC requests to the database
```
