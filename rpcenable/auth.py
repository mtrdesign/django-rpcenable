"""
Authentication functions to be used by the RPC playground
"""
import hmac
import hashlib
import functools
import time
import os
import string

from django.core.cache import cache
from django.utils.timezone import now
from django.utils.importlib import import_module
from django.conf import settings

from rpcenable.models import APIUser
from rpcenable.registry import XMLRPCPoint
from xmlrpclib import Fault

NONCE_MIN_LEN = 16
# Validity period used for nonce invalidation and timestamp margin
VALIDITY = 300
# Name of the nonce keys in the cache
NONCE_KEY_FORMAT = '_apinonce::%s::%s'
# Alphabet to choose nonce's random characters from
NONCE_ALPHABET = string.ascii_letters + string.digits + '-_'

ERR_NONCE_SHORT = 401
ERR_NONCE_USED = 402
ERR_BAD_TS = 403
ERR_USER_MISSING = 404
ERR_USER_MULTIPLE = 405
ERR_BAD_SIGNATURE = 406


class AuthError (Fault):
    """Indicates failed Authentication"""
    pass

def generate_auth_args (username, secret):
    """
    Generate the required authentication arguments, based on the given
    username and shared secret.
    """
    l = len(NONCE_ALPHABET)
    nonce = ''.join(NONCE_ALPHABET[ord(os.urandom(1)) % l] for i in xrange(NONCE_MIN_LEN))
    ts = int(time.time())
    return (nonce, ts, username, compute_signature (nonce, ts, username, secret))

def compute_signature (nonce, ts, username, secret):
    """Computes a Sha256 HMAC signature based on the input"""
    s = hmac.new(str(secret), '%s;%s;%s' % (nonce, ts, username), digestmod=hashlib.sha256)
    return s.hexdigest()

def mark_nonce_used (nonce, username):
    """
    Cache the given nonce as used for this particular user.
    """
    cache.set(NONCE_KEY_FORMAT % (username, nonce), 1, VALIDITY)

def check_nonce_bad (nonce, username):
    """
    Check if the provided nonce is valid, e.g. it's long enough and has not
    been used before. In addition, mark the nonce as used
    """
    if len(nonce) < NONCE_MIN_LEN:
        raise AuthError (ERR_NONCE_SHORT, 'Nonce is too short (%d < %d)' % (len(nonce), NONCE_MIN_LEN))
    used = cache.get(NONCE_KEY_FORMAT % (username, nonce))
    if used:
        raise AuthError (ERR_NONCE_USED,'Nonce %s is already used' % nonce)
    mark_nonce_used (nonce, username)


def check_timestamp (ts):
    """
    Check if the provided teimstamp is within the validity margin of the current time.
    """
    if not (str(ts).isdigit() and abs(time.time() - int(ts)) < VALIDITY):
        raise AuthError (ERR_BAD_TS,'Provided timestamp is invalid: %s' % ts)

def get_user (username, user_model=None, user_filter=None):
    """
    Retrieves a user object corresponding to the given username
    """
    user_model = user_model or APIUser
    qs = user_model.objects.all()
    if user_filter:
        qs = qs.filter(**user_filter)
    try:
        u = qs.get(username=username, active=True)
    except user_model.DoesNotExist:
        raise AuthError (ERR_USER_MISSING, 'Provided username cannot be found: %s' % username)
    except user_model.MultipleObjectsReturned:
        raise AuthError (ERR_USER_MULTIPLE, 'Multiple users found with username: %s' % username)
    return u

def authenticate (nonce, ts, username, signature, user_model=None, user_filter=None):
    """Checks all of the requisites for a successful auth"""
    check_nonce_bad (nonce, username)
    check_timestamp (ts)
    user = get_user (username, user_model=user_model, user_filter=user_filter)
    mysig = compute_signature (nonce, ts, username, user.secret)
    if not mysig==signature:
        raise AuthError (ERR_BAD_SIGNATURE, 'Signature is invalid: %s!=%s' % (mysig, signature))
    user.last_login = now()
    user.save()
    return user

def rpcauth (fn=None, user_model=None, user_filter=None):
    """
    Decorator that strips the arguments (nonce, ts, username, signature) and replaces them
    with the hooked-up User instance as a first arg upon successful authentication.
    The decorated function MUST accept the user instance as a first argument.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(nonce, ts, username, signature, *args, **kwargs):
            user = authenticate(nonce, ts, username, signature, user_model=user_model, user_filter=user_filter)
            return fn(user, *args, **kwargs)
        return wrapper
    if fn:
        return decorator(fn)
    else:
        return decorator
    return wrapper

def noauth(f):
    """
    Decorator that strips the arguments (nonce, ts, username, signature) and replaces them
    with None instead of a User instance; for RPC methods that do not require authentication.
    """
    @functools.wraps(f)
    def wrapper(nonce, ts, username, signature, *args, **kwargs):
        return f(None, *args, **kwargs)
    return wrapper

class AuthXMLRPCPoint(XMLRPCPoint):
    """
    XMLRPC endpoint for outgoing authenticated calls,

    Automatically prepends the authentication arguments returned by
    `generate_auth_args(user, secret)` to the list of XMLRPC
    """
    def __init__ (self, user, secret, *args, **kwargs):
        # pass down a function that prepends auth arguments to the regulart API Call args
        kwargs['param_hook'] = lambda x: generate_auth_args(user, secret) + x
        kwargs['allow_none'] = True
        return XMLRPCPoint.__init__(self, *args, **kwargs)   # old-style inheritance
