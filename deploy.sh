#!/bin/bash
# Script de deploy para Oracle Cloud VM (Ubuntu 22.04)
# Roda LADO A LADO com o deploy do MTJL_BookingAI_Beauty na mesma VM —
# Postgres/Nginx/Certbot já devem estar instalados por aquele deploy.
# Uso: bash deploy.sh

set -e

DOMAIN="mtjltechnology.com"
PORT="8010"

APP_DIR="/home/ubuntu/mtjl_website"
DB_NAME="mtjl_website"
DB_USER="mtjl_website"
DB_PASS=$(openssl rand -hex 16)

echo "=== [1/5] Configurando PostgreSQL ==="
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true

echo ""
echo ">>> DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"
echo ">>> Guarde essa string — você vai precisar no .env"
echo ""

echo "=== [2/5] Clonando projeto ==="
if [ ! -d "$APP_DIR" ]; then
    git clone https://github.com/mtjltechnology/mtjl_website.git "$APP_DIR"
else
    cd "$APP_DIR" && git pull
fi

echo "=== [3/5] Configurando Python ==="
cd "$APP_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

echo ""
echo ">>> Agora crie o arquivo .env:"
echo ">>> nano $APP_DIR/.env"
echo ">>> Copie o .env.example, preencha as chaves e a DATABASE_URL acima."
echo ">>> BOOKING_MASTER_API_KEY precisa ser IGUAL ao MASTER_API_KEY do .env"
echo ">>> do MTJL_BookingAI_Beauty (/home/ubuntu/bookingai/.env)."
echo ""
read -p "Pressione ENTER após criar o .env para continuar..."

echo "=== [4/5] Migrando dados de pilotqasubscriber (produto → site) ==="
echo ">>> Rode manualmente, se ainda não migrou:"
echo ">>>   pg_dump -t pilotqasubscriber -Fc bookingai > /tmp/pilotqasubscriber.dump"
echo ">>>   pg_restore -d $DB_NAME --data-only --table=pilotqasubscriber /tmp/pilotqasubscriber.dump"
read -p "Pressione ENTER após migrar os dados (ou pular, se banco novo) para continuar..."

echo "=== [5/5] Iniciando serviço com PM2 ==="
cd "$APP_DIR"
source .venv/bin/activate

pm2 start \
    ".venv/bin/gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 127.0.0.1:$PORT" \
    --name "mtjl-website" \
    --cwd "$APP_DIR"

pm2 save

echo ""
echo "======================================"
echo "  Deploy concluído!"
echo "======================================"
echo "Serviço rodando em: http://127.0.0.1:$PORT"
echo ""
echo ">>> Falta editar o bloco Nginx de $DOMAIN pra rotear por path entre"
echo ">>> este serviço (porta $PORT) e o bookingai-api (porta 8000)."
echo ">>> Ver tabela de roteamento no plano de migração / CLAUDE.md."
echo ""
echo "Comandos úteis:"
echo "  pm2 logs mtjl-website       → logs"
echo "  pm2 restart mtjl-website    → reiniciar"
