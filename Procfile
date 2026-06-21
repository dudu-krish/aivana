release: python -c "from app.services.database import init_db; init_db()"
web: gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --timeout 120 --access-logfile -
