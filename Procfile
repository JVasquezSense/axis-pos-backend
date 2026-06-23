release: python3 manage.py migrate --noinput && python3 manage.py collectstatic --noinput
web: daphne -b 0.0.0.0 -p $PORT config.asgi:application
worker: celery -A config worker -l info
