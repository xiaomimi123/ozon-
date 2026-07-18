import pathlib
import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[2]   # ozon-listing-auto/


def test_prod_compose_is_valid_and_hardened():
    data = yaml.safe_load((_ROOT / "docker-compose.prod.yml").read_text())
    svcs = data["services"]
    # 内部服务不发布公网端口
    for name in ("db", "redis", "api", "worker"):
        assert name in svcs, f"缺少服务 {name}"
        assert "ports" not in svcs[name], f"{name} 不应对公网发布端口"
    # nginx 对外 80/443
    nginx_ports = " ".join(str(p) for p in svcs["nginx"]["ports"])
    assert "443" in nginx_ports and "80" in nginx_ports
    assert "certbot" in svcs, "缺少 certbot 服务"


def test_prod_deploy_files_exist():
    assert (_ROOT / "deploy" / "nginx.prod.conf").exists()
    assert (_ROOT / "deploy" / "certbot-init.sh").exists()
    assert (_ROOT / ".env.prod.example").exists()
    conf = (_ROOT / "deploy" / "nginx.prod.conf").read_text()
    assert "listen 443 ssl" in conf and "Strict-Transport-Security" in conf
    assert "/api/" in conf and "/ws/" in conf and "Upgrade" in conf
    assert "301 https" in conf                        # 80→443 强制跳转


def test_certbot_init_uses_standalone_bootstrap_not_nginx_first():
    # 回归测试：首次签证必须用 certbot --standalone（不依赖 nginx 已启动），
    # 避免「nginx 需证书才能启动、证书又需 nginx 服务挑战」的 bootstrap 死锁。
    script = (_ROOT / "deploy" / "certbot-init.sh").read_text()
    assert "certonly" in script
    assert "--standalone" in script
    assert "up -d nginx" not in script                 # 不应在签证前先起 nginx

    # 回归测试：docker compose 插值整份 compose 文件时会先校验 POSTGRES_PASSWORD 等
    # `${VAR:?}` 变量，若不带 --env-file .env.prod 会在 certbot 启动前就直接中止。
    for line in script.splitlines():
        if "docker compose -f docker-compose.prod.yml" in line:
            assert "--env-file" in line, f"缺少 --env-file: {line!r}"
