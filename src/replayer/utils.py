import asyncio
import hashlib
import logging
import os
import ssl
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Literal, Optional, TypedDict, cast

import aiohttp
from melobot import get_bot
from melobot.log import GenericLogger, get_logger
from melobot.protocols.onebot.v11 import Adapter, Segment
from melobot.utils.common import _DEFAULT_ID_WORKER

from .msg import Record, SegmentHandle

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.set_ciphers("DEFAULT")
SSL_CONTEXT.options |= ssl.OP_NO_SSLv2
SSL_CONTEXT.options |= ssl.OP_NO_SSLv3
SSL_CONTEXT.options |= ssl.OP_NO_TLSv1
SSL_CONTEXT.options |= ssl.OP_NO_TLSv1_1
SSL_CONTEXT.options |= ssl.OP_NO_COMPRESSION

_origin_get_logger = logging.getLogger


def _patch_get_logger(name: str | None = None) -> logging.Logger:
    if name != "sqlalchemy.engine.Engine":
        return _origin_get_logger(name)
    else:
        return get_logger()


logging.getLogger = _patch_get_logger  # type: ignore


def get_id() -> int:
    return _DEFAULT_ID_WORKER.get_id()


def make_record(
    sh: SegmentHandle,
    type: str,
    text: str | None = None,
    data: str | None = None,
) -> Record:
    return Record(
        sid=get_id(),
        time=sh.time,
        eid=sh.eid,
        mid=sh.mid,
        gid=sh.gid,
        uid=sh.uid,
        type=type,
        text=text,
        nickname=sh.nickname,
        data=data,
        idx=sh.idx,
    )


class _FaceTextData(TypedDict):
    text: str
    faces: str


FACE_TEXT_TYPE = "facetxt"
FaceTextSegment = Segment.add_type(Literal[FACE_TEXT_TYPE], _FaceTextData)  # type: ignore


class _MfaceData(TypedDict):
    url: str


MFACE_TYPE = "mface"
MfaceSegment = Segment.add_type(Literal[MFACE_TYPE], _MfaceData)  # type: ignore


_adapter = cast(Adapter, get_bot().get_adapter(Adapter))
assert _adapter is not None, "初始化工具模块时，无法获取到 ob11 适配器"


@_adapter.when_validate_error("event")
async def _patch_mface(raw_dic: dict[str, Any], _: Exception) -> None:
    if raw_dic.get("message_type") == "group":
        for seg in raw_dic["message"]:
            if seg["type"] == "mface":
                url_v = seg["data"].get("url")
                if url_v is None:
                    seg["data"]["url"] = ""


HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.96 Safari/537.36"
}


@asynccontextmanager
async def async_http(
    url: str,
    method: Literal["get", "post"],
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    data: Optional[dict] = None,
    json: Optional[dict] = None,
    proxy: str | None = None,
    verify_ssl: bool = True,
) -> AsyncGenerator[aiohttp.ClientResponse, None]:
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(verify_ssl=verify_ssl, ssl_context=SSL_CONTEXT),
        headers=headers,
    ) as http_session:
        kwargs: dict[str, Any] = {}
        if proxy:
            kwargs["proxy"] = proxy
        if json:
            kwargs["json"] = json
        if params:
            kwargs["params"] = params
        if method == "get":
            async with http_session.get(url, **kwargs) as resp:
                yield resp
        else:
            async with http_session.post(url, data=data, **kwargs) as resp:
                yield resp


class BinaryDataManager:
    def __init__(self, root_path: str | Path):
        self.root = (
            root_path.resolve()
            if isinstance(root_path, Path)
            else Path(root_path).resolve()
        )
        self.default_dir = self.root / "none"
        os.makedirs(str(self.default_dir), exist_ok=True)

        self.retry_delays = (1, 2, 4, 8, 16, 32, 64)

    @property
    def logger(self) -> GenericLogger:
        return get_logger()

    async def store(self, url: str, timestamp: int | None) -> str:
        md5 = ""
        try:
            for delay in self.retry_delays:
                async with async_http(url, "get", headers=HEADERS) as resp:
                    if resp.status != 200:
                        await asyncio.sleep(delay)
                        continue
                    content = await resp.content.read()
                    assert len(content) > 0, "获取的数据为空字节"

                    if timestamp:
                        date = datetime.fromtimestamp(timestamp)
                        img_dir = self.root / str(date.year) / str(date.month)
                        os.makedirs(str(img_dir), exist_ok=True)
                    else:
                        img_dir = self.default_dir

                    md5 = hashlib.md5(content).hexdigest()
                    img_path = img_dir / f"{md5}.bin"
                    if not img_path.exists():
                        with open(img_path, "wb") as fp:
                            fp.write(content)
                        self.logger.debug(f"二进制数据已存储，源：{url}")
                    else:
                        self.logger.debug(f"二进制数据已存在，跳过存储，源：{url}")
                    break
        except Exception:
            self.logger.exception(f"存储数据时发生错误，时间：{timestamp}，源：{url}")
        return md5


class ImageManager(BinaryDataManager):
    def __init__(self, root_path: str | Path) -> None:
        super().__init__(root_path)


class AudioManager(BinaryDataManager):
    def __init__(self, root_path: str | Path) -> None:
        super().__init__(root_path)


class VideoManager(BinaryDataManager):
    def __init__(self, root_path: str | Path) -> None:
        super().__init__(root_path)


class MFaceManager(BinaryDataManager):
    def __init__(self, root_path: str | Path) -> None:
        super().__init__(root_path)
