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

NONCE_MIN_LEN = 16
# Validity period used for nonce invalidation and timestamp margin
VALIDITY = 300
# Name of the nonce keys in the cache
NONCE_KEY_FORMAT = '_apinonce::%s::%s'
# Alphabet to choose nonce's random characters from
NONCE_ALPHABET = string.ascii_letters + string.digits + '-_'


class AuthError (Exception):
    """Indicates failed Authentication"""
    pass

def generate_auth_args (username, secret):
    """
    Generate the required authentication arguments, based on the given
    username and shared secret.
    """
    l = len(NONCE_ALPHABET)
    nonce = ''.join(NONCE_ALPHABET[ord(os.urandom(1)) % l] for i in xrange(NONCE_MIN_LEN))
    ts = str(int(time.time()))
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
        raise AuthError ('Nonce is too short (%d < %d)' % (len(nonce), NONCE_MIN_LEN))
    used = cache.get(NONCE_KEY_FORMAT % (username, nonce))
    if used:
        raise AuthError ('Nonce %s is already used' % nonce)
    mark_nonce_used (nonce, username)


def check_timestamp (ts):
    """
    Check if the provided teimstamp is within the validity margin of the current time.
    """
    if not (str(ts).isdigit() and abs(time.time() - int(ts)) < VALIDITY):
        raise AuthError ('Provided timestamp is invalid: %s' % ts)

def get_user (username):
    """
    Retrieves a user object corresponding to the given username
    """
    try:
        u = APIUser.objects.get (username=username, active = True)
    except APIUser.DoesNotExist:
        raise AuthError ('Provided username cannot be found: %s' % username)
    except APIUser.MultipleObjectsReturned:
        raise AuthError ('Multiple users found with username: %s' % username)
    return u

def authenticate (nonce, ts, username, signature):
    """Checks all of the requisites for a successful auth"""
    check_nonce_bad (nonce, username)
    check_timestamp (ts)
    user = get_user (username)
    mysig = compute_signature (nonce, ts, username, user.secret)
    if not mysig==signature:
        raise AuthError ('Signature is invalid: %s!=%s' % (mysig, signature))
    user.last_login = now()
    user.save()
    return user

def rpcauth (f):
    """
    Decorator that strips the arguments (nonce, ts, username, signature) and replaces them
    with the hooked-up User instance as a first arg upon successful authentication.
    The decorated function MUST accept the user instance as a first argument.
    """
    @functools.wraps(f)
    def wrapper (nonce, ts, username, signature, *args, **kwargs):
        user = authenticate (nonce, ts, username, signature)
        return f(user, *args, **kwargs)
    return wrapper
