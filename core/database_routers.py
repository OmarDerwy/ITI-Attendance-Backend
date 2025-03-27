# """
# Defined here is the database router to make sure all modification and read operations on the users app happen on the remote database and anything else happens on the local database
# Relations between models on the local and remote database are allowed
# """
# class UserDatabaseRouter:
#     def db_for_read(self, model, **hints):
#         if model._meta.app_label in ['users', 'auth', 'contenttypes']:
#              return 'remote_db'
#         return 'default'

#     def db_for_write(self, model, **hints):
#         if model._meta.app_label in ['users', 'auth', 'contenttypes']:
#             return 'remote_db'
#         return 'default'
#     def allow_relation(self, obj1, obj2, **hints):
#             return True

#     def allow_migrate(self, db, app_label, model_name=None, **hints):
#         if app_label in ['users', 'auth', 'contenttypes']:
#             return db == 'remote_db'
#         return db == 'default'