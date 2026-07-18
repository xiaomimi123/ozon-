#!/usr/bin/env sh
# 首次签发 Let's Encrypt 证书（服务器执行一次；域名须已解析到本机公网 IP，且 80 端口空闲）。
# 用 --standalone：certbot 自己临时占用 80 完成 HTTP-01 挑战，此时 nginx 尚未启动，
# 从而避开「nginx 需证书才能启动、证书又需 nginx 服务挑战」的先有鸡还是先有蛋问题。
# 用法：DOMAIN=example.com CERTBOT_EMAIL=you@x.com sh deploy/certbot-init.sh
set -e
: "${DOMAIN:?需设置 DOMAIN}"
: "${CERTBOT_EMAIL:?需设置 CERTBOT_EMAIL}"

# 确保没有别的容器占用 80（若之前起过全栈，先停 nginx）
docker compose -f docker-compose.prod.yml stop nginx 2>/dev/null || true

# standalone 一次性签发（临时把宿主 80 映射给 certbot 容器）
docker compose -f docker-compose.prod.yml run --rm -p 80:80 --entrypoint certbot certbot \
  certonly --standalone \
  -d "$DOMAIN" --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email

echo "证书签发完成。现在执行："
echo "  docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build"
echo "nginx 启动时即可加载 /etc/letsencrypt/live/$DOMAIN/ 下的证书；后续续期由 certbot 容器 webroot 自动完成。"
