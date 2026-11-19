#este script arranca todo el proyecto de una
cd "$(dirname "$0")"

if ! pg_isready -q 2>/dev/null; then
  echo "Encendiendo PostgreSQL 17..."
  brew services start postgresql@17
  sleep 2
fi

source .venv/bin/activate

python manage.py migrate --noinput

lsof -ti :8000 | xargs kill -9 2>/dev/null
sleep 1

echo ""
echo "Abre http://127.0.0.1:8000 en el navegador"
python manage.py runserver
