django-rpcenable
================

Simple module to enable exposing functions over XML-RPC

Configuration entries
================
```
# RPCEnable Settings
RPCENABLE_USER_MODEL = 'import.path.to.MyAPIUserModel' # Model to hook up the rpcenable.auth to
RPCENABLE_LOG_INCOMING = True   # Whether to log incoming RPC requests to the database
```
