#!/usr/bin/env sh
# 首次签发 Let's Encrypt 证书（服务器上执行一次；域名须已解析到本机公网 IP）。
# 用法：DOMAIN=example.com CERTBOT_EMAIL=you@x.com sh deploy/certbot-init.sh
set -e
: "${DOMAIN:?需设置 DOMAIN}"
: "${CERTBOT_EMAIL:?需设置 CERTBOT_EMAIL}"

# 先起 nginx（提供 80 端口 ACME 挑战 webroot）
docker compose -f docker-compose.prod.yml up -d nginx

# webroot 方式签发
docker compose -f docker-compose.prod.yml run --rm --entrypoint certbot certbot \
  certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email

# 重载 nginx 以加载新证书
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
echo "证书签发完成。现在可 docker compose -f docker-compose.prod.yml up -d 起全栈。"
