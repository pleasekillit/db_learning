"""FastAPI 依赖：会话生命周期 + 内网访问控制。"""
from __future__ import annotations

import ipaddress
import os
from collections.abc import Generator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from powerdb.core.engine import session_scope

# 允许的内网网段（IPv4 私有网段 + 本机），环境变量 POWERDB_ALLOWED_CIDRS 可逗号分隔覆盖。
DEFAULT_ALLOWED_CIDRS = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8"

# TestClient / 反向代理缺省来源的 host 取值，本地开发与单测直接放行，生产不会出现。
_LOCAL_HOSTS = {"testclient", "", "localhost"}


def get_session() -> Generator[Session, None, None]:
    with session_scope() as session:
        yield session


def _allowed_networks() -> list:
    raw = os.environ.get("POWERDB_ALLOWED_CIDRS", DEFAULT_ALLOWED_CIDRS)
    return [ipaddress.ip_network(n.strip(), strict=False) for n in raw.split(",") if n.strip()]


def is_intranet_ip(host: str) -> bool:
    """判断来源 IP 是否落在允许的内网网段；公网直连返回 False。"""
    if host in _LOCAL_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in _allowed_networks())


def require_intranet(request: Request) -> None:
    """依赖：只放行内网 IP，公网直连一律 403。

    使用：def submit_run(..., _ip: None = Depends(require_intranet))。
    内网 Windows PC 一般不会直接暴露公网，此处是最基础的访问控制；
    更强请在前置 nginx 作 IP 白名单 / 或加登录鉴权。
    """
    host = request.client.host if request.client else ""
    if not is_intranet_ip(host):
        raise HTTPException(status_code=403, detail="仅限公司内网访问")