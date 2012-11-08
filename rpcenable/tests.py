"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""
import threading
import time
import os

from django.test import TestCase
from django.test.utils import override_settings
from django.core import mail
from django.conf import settings


from rpcenable.abstractmodels import BaseAPIUser, APIUserAdmin, SampleUser
from rpcenable import async, auth

from django.db import models
from django.core.mail import mail_admins

def wait_threads():
    for thread in threading.enumerate():
        if thread is not threading.currentThread():
            thread.join()

class AsycTest(TestCase):

    def test_asyc_ok (self):
        wait = 3
        @async.postpone
        def test_func (wait):
            # we use mail_admins as a simple method of IPC
            time.wait(wait)
            mail.send_mail ('Async test', 'Async test', 'test@example.com', ['test@example.com'])
            print 'Sent mail'
            return 1
        start_time = time.time()
        self.assertEqual (test_func(), None)
        self.assertLess (time.time() - start_time, wait, 'Too much wait... threading seems not to work')
        async._cleanup()
        self.assertEqual (len(mail.outbox), 1)

    def test_asyc_exception (self):
        @async.postpone
        def test_func ():
            # raising an exception should result in an email to admins
            raise ValueError('Foo')
        # we should get no exception here
        test_func()
        # We should get an email to admins once the thread finishes
        async._cleanup()
        self.assertEqual (len(mail.outbox), 1)
        self.assertItemsEqual(mail.outbox[0].recipients(), [a[1] for a in settings.ADMINS])


class AuthTest(TestCase):
    def setUp (self):
        self.uname = 'u1'
        self.secret = 's1'
        self.user = auth.APIUser(username = self.uname, secret = self.secret, active = True)
        self.user.save()

    def test_globals(self):
        # os.urandom returns a value in 0-255; to avoid bias, we should use
        # an alphabet with a lenth that divides 256
        self.assertEqual (256 % len(auth.NONCE_ALPHABET), 0)
        # Make sure our Cache key has two placeholders
        self.assertEqual (len(auth.NONCE_KEY_FORMAT.split('%s')), 3)

    def test_generate_auth_args (self):
        # generate_auth_args is time/randomness dependent so no ref value test
        nonce, ts, ret_user, signature = auth.generate_auth_args(self.uname,self.secret)
        self.assertEqual (len(nonce), auth.NONCE_MIN_LEN)
        self.assertIsInstance (ts, int)
        self.assertGreater (ts, 0)
        self.assertEqual (ret_user, self.uname)
        self.assertIsInstance (signature, str)
        self.assertEqual (len(signature), 64) # lengtho of sha256 hmac

    def test_compute_signature (self):
        nonce = 'sGL8uZQ8Lo1dVo49'
        ts = 1352371368
        self.assertEqual (auth.compute_signature(nonce,ts,self.uname,self.secret),
            '7ab7bbbc9847c91b327e07394b9e80aad4975e2f90075597849d1b8e2bec4f74')

    def test_nonce_invalidation (self):
        user = 'u1'
        # get a random nonce
        nonce = ''.join(auth.NONCE_ALPHABET[ord(os.urandom(1)) % len(auth.NONCE_ALPHABET)] for i in xrange(auth.NONCE_MIN_LEN))
        # there is a very small chance for collision
        self.assertEqual (auth.check_nonce_bad(nonce, self.uname), None)
        self.assertRaises (auth.AuthError, auth.check_nonce_bad, nonce, self.uname)

    def test_timestamp_verification (self):
        t = int(time.time())
        auth.check_timestamp (t) # no exception if timestamp is OK
        self.assertRaises(auth.AuthError, auth.check_timestamp, t - auth.VALIDITY -1 )
        self.assertRaises(auth.AuthError, auth.check_timestamp, t + auth.VALIDITY +1 )

    def test_user_verification (self):
        self.assertEqual (auth.get_user (self.uname), self.user)
        self.assertRaises (auth.AuthError, auth.get_user, self.uname + 'dummy')
        # test if we are skipping inactive users
        self.user.active = False
        self.user.save()
        self.assertRaises (auth.AuthError, auth.get_user, self.uname)

    def test_authetication (self):
        # generate auth details
        details = auth.generate_auth_args (self.uname, self.secret)
        self.assertEqual(auth.authenticate(*details), self.user)
        self.assertRaises(auth.AuthError, auth.authenticate, *details) # another auth with the same details should be impossible

    def test_rpcauth_decorator (self):
        somevar = 'Foo'
        @auth.rpcauth
        def foo (user, var):
            return user, var
        details = auth.generate_auth_args (self.uname, self.secret)
        user,var = foo(*(details + (somevar,)))
        self.assertEqual (user, self.user)
        self.assertEqual (var, somevar)
        # check with repeated auth
        self.assertRaises (auth.AuthError, foo, *(details + (somevar,)))
        # check with otherwise incorrect auth
        details = auth.generate_auth_args (self.uname , self.secret + 'Dummy')
        self.assertRaises (auth.AuthError, foo, *(details + (somevar,)))











