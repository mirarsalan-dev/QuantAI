import auth
import config

print('FIREBASE_AVAILABLE =', getattr(config, 'FIREBASE_AVAILABLE', False))

username = 'smoke_test_user'
password = 'Sm0keTest!'

print('Creating user...')
created = auth.create_user(username, password)
print('create_user ->', created)

print('Logging in...')
logged = auth.login_user(username, password)
print('login_user ->', logged)

# Cleanup
if getattr(config, 'db', None) is not None:
    try:
        config.db.collection('users').document(username).delete()
        print('Deleted test user from Firebase')
    except Exception as e:
        print('Failed to delete test user:', e)
else:
    print('DB not available; no cleanup')
