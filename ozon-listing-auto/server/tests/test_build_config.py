"""构建配置核对：确保真实 CLIP 的 [ml] 依赖 + INSTALL_ML 构建路径 + compose worker 参数正确。"""
import pathlib
import tomllib

_SERVER = pathlib.Path(__file__).resolve().parents[1]      # ozon-listing-auto/server
_ROOT = _SERVER.parent                                     # ozon-listing-auto


def test_pyproject_ml_extra_has_torch_and_cnclip():
    data = tomllib.loads((_SERVER / "pyproject.toml").read_text())
    ml = data["project"]["optional-dependencies"]["ml"]
    joined = " ".join(ml).lower()
    assert "torch" in joined and "cn-clip" in joined       # 真实 CLIP 依赖


def test_dockerfile_install_ml_branch():
    df = (_SERVER / "Dockerfile").read_text()
    assert "INSTALL_ML" in df and ".[dev,ml]" in df        # INSTALL_ML=true 装 [ml]


def test_compose_worker_has_install_ml_and_embedder():
    dc = (_ROOT / "docker-compose.yml").read_text()
    assert "INSTALL_ML" in dc and "EMBEDDER" in dc          # worker 传构建 arg + env
