#!/bin/bash
# Script de deploy para GCP Compute Engine (projeto mtjl-booking-ai-beauty,
# instancia bookingai-beauty, zone us-central1-a).
# Roda LADO A LADO com o deploy do MTJL_BookingAI_Beauty na mesma VM —
# Postgres/Nginx/Certbot já devem estar instalados por aquele deploy.
# Acesso: gcloud compute ssh bookingai-beauty --project mtjl-booking-ai-beauty --zone us-central1-a
# Uso (setup inicial): bash deploy.sh
# Deploy recorrente (código já em produção): pular direto pro passo 5
# (git pull + pm2 restart) — passos 1 e 4 são só para VM nova.

set -e

DOMAIN="mtjltechnology.com"
PORT="8011"

APP_DIR="/home/murilomattos/mtjl_website"
DB_NAME="mtjl_website"
DB_USER="mtjl_website"
DB_PASS=$(openssl rand -hex 16)

echo "=== [1/5] Configurando PostgreSQL (só necessário na primeira vez, banco já existe em produção) ==="
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

echo "=== [4/5] Migrando dados de pilotqasubscriber (produto → site), só na primeira vez ==="
echo ">>> Rode manualmente, se ainda não migrou:"
echo ">>>   pg_dump -t pilotqasubscriber -Fc bookingai > /tmp/pilotqasubscriber.dump"
echo ">>>   pg_restore -d $DB_NAME --data-only --table=pilotqasubscriber /tmp/pilotqasubscriber.dump"
read -p "Pressione ENTER após migrar os dados (ou pular, se banco novo) para continuar..."

echo "=== [5/5] Iniciando serviço com PM2 ==="
cd "$APP_DIR"
source .venv/bin/activate

pm2 start \
    ".venv/bin/uvicorn main:app --host 127.0.0.1 --port $PORT --proxy-headers --forwarded-allow-ips=127.0.0.1" \
    --name "mtjl-website" \
    --cwd "$APP_DIR"

pm2 save

echo ""
echo "======================================"
echo "  Deploy concluído!"
echo "======================================"
echo "Serviço rodando em: http://127.0.0.1:$PORT"
echo ""
echo ">>> Nginx já configurado em bloco compartilhado com outros produtos"
echo ">>> da mesma VM: /etc/nginx/sites-enabled/mtjltechnology (roteamento"
echo ">>> por path, não por porta única). Não mexer sem ver o roteamento"
echo ">>> completo daquele arquivo primeiro."
echo ""
echo ">>> DOMÍNIO DO LARCLÍNICA (www.larclinicahealth.com)"
echo ">>> A página institucional do LarClínica saiu de mtjltechnology.com/larclinica e"
echo ">>> passou a ser servida por esta mesma aplicação, escolhida pelo cabeçalho Host."
echo ">>> O vhost /etc/nginx/sites-enabled/larclinicahealth já existe, com certificado"
echo ">>> próprio em /etc/letsencrypt/live/larclinicahealth.com, mas na versão original"
echo ">>> ele fazia 302 de tudo pra mtjltechnology.com/larclinica. Isso tem que virar"
echo ">>> roteamento por path, senão o 301 do caminho antigo e o 302 do domínio novo"
echo ">>> formam loop. Bloco 443 esperado:"
cat <<'NGINX'

    server {
        listen 443 ssl;
        server_name larclinicahealth.com www.larclinicahealth.com;

        ssl_certificate /etc/letsencrypt/live/larclinicahealth.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/larclinicahealth.com/privkey.pem;

        # Site institucional do LarClínica: mtjl_website (8011). Só a raiz e o que a
        # página precisa. proxy_set_header Host $host é obrigatório: é por ele que a
        # aplicação sabe que a requisição chegou pelo domínio do LarClínica e entrega
        # larclinica.html na raiz em vez da home da MTJL.
        location = / { include /etc/nginx/snippets/larclinica_site.conf; }
        location = /larclinica_contact { include /etc/nginx/snippets/larclinica_site.conf; }
        location = /robots.txt { include /etc/nginx/snippets/larclinica_site.conf; }
        location = /sitemap.xml { include /etc/nginx/snippets/larclinica_site.conf; }
        location = /favicon.ico { include /etc/nginx/snippets/larclinica_site.conf; }
        location /static/website/ { include /etc/nginx/snippets/larclinica_site.conf; }
        location /static/brand/ { include /etc/nginx/snippets/larclinica_site.conf; }

        # Caminho aposentado pedido no domínio novo: um salto só, pra própria raiz.
        location = /larclinica { return 301 https://www.larclinicahealth.com/; }

        # Todo o resto continua sendo o APP do produto, que hoje mora atrás de
        # mtjltechnology.com/larclinica/ (34.74.45.49:8080). Mantido como estava:
        # /login, /paciente e companhia seguem funcionando pelos mesmos links.
        location / {
            return 302 https://mtjltechnology.com/larclinica$request_uri;
        }
    }

    # /etc/nginx/snippets/larclinica_site.conf
    proxy_pass http://127.0.0.1:8011;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

NGINX
echo ">>> ORDEM DE APLICAÇÃO IMPORTA: nginx primeiro, código depois."
echo ">>>   1. sudo nginx -t && sudo systemctl reload nginx"
echo ">>>   2. cd $APP_DIR && git pull && pm2 restart mtjl-website"
echo ">>> Invertendo a ordem, /larclinica passa a 301 pro domínio novo enquanto o"
echo ">>> domínio novo ainda 302 de volta pra /larclinica: loop."
echo ">>> Entre o passo 1 e o 2 a raiz do domínio novo serve a home da MTJL por"
echo ">>> alguns segundos, o que é preferível ao loop."
echo ""
echo "Deploy recorrente (código já em produção, sem mudança de dependência):"
echo "  cd $APP_DIR && git pull && pm2 restart mtjl-website"
echo ""
echo "Comandos úteis:"
echo "  pm2 logs mtjl-website       → logs"
echo "  pm2 restart mtjl-website    → reiniciar"
