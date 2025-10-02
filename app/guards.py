# from functools import wraps
# from flask import abort
# from flask_login import current_user

# def roles_required(*roles):
#     def wrap(fn):
#         @wraps(fn)
#         def inner(*a, **kw):
#             if not current_user.is_authenticated: abort(401)
#             if current_user.role not in roles:    abort(403)
#             return fn(*a, **kw)
#         return inner
#     return wrap
