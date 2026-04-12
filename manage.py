import os
import sys

from app import app

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
        host = os.getenv('HOST', '0.0.0.0')
        port = int(os.getenv('PORT', '5000'))
        debug = os.getenv('FLASK_DEBUG', 'True').lower() in ('1', 'true', 'yes')
        app.run(host=host, port=port, debug=debug)
    else:
        print('Usage: python manage.py runserver')
