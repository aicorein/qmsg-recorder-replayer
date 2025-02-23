import os
from asyncio import Lock
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator

from melobot.protocols.onebot.v11 import Segment
from sqlalchemy.ext.asyncio.engine import create_async_engine
from sqlmodel import Field, Index, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from .base import DB_DIR


class Record(SQLModel, table=True):
    __tablename__ = "segments"
    sid: int = Field(primary_key=True)
    time: int | None = Field(index=True)
    eid: int = Field(index=True)
    mid: int | None = Field(index=True)
    gid: int | None
    uid: int
    type: str
    text: str | None
    nickname: str | None
    data: str | None
    idx: int


Index(
    "unique_seg",
    Record.time,  # type: ignore
    Record.mid,  # type: ignore
    Record.idx,  # type: ignore
    unique=True,
    sqlite_where=(Record.time.isnot(None) & Record.mid.isnot(None)),  # type: ignore
)
Index("txt_idx", Record.text, sqlite_where=(Record.text.isnot(None)))  # type: ignore
Index(
    "cover_idx",
    Record.time,  # type: ignore[arg-type]
    Record.uid,  # type: ignore[arg-type]
    Record.text,  # type: ignore[arg-type]
    sqlite_where=(Record.text.isnot(None)),  # type: ignore
)
Index("time_uid_idx", Record.time, Record.uid)  # type: ignore[arg-type]
Index("time_scope_idx", Record.time, Record.gid, Record.uid)  # type: ignore[arg-type]


@dataclass(kw_only=True)
class SegmentTag:
    eid: int
    mid: int | None
    time: int | None
    gid: int | None
    uid: int
    nickname: str | None


@dataclass(kw_only=True)
class SegmentHandle(SegmentTag):
    seg: Segment
    idx: int


class MsgDB:
    def __init__(self) -> None:
        self._prepare()

        self.url = rf"sqlite+aiosqlite:///{str(self.path)}"
        self.engine = create_async_engine(
            self.url,
            connect_args={"check_same_thread": False, "timeout": 600},
            echo=False,
        )
        self._started = False
        self._lock = Lock()

    def _prepare(self) -> None:
        self.root_dir = DB_DIR / "messages"
        self.imgs_dir = self.root_dir / "images"
        self.audios_dir = self.root_dir / "audios"
        self.videos_dir = self.root_dir / "videos"
        self.mface_dir = self.root_dir / "mfaces"
        self.path = self.root_dir / "messages.db"

        if not self.root_dir.exists():
            os.mkdir(str(self.root_dir))
        if not self.imgs_dir.exists():
            os.mkdir(str(self.imgs_dir))
        if not self.audios_dir.exists():
            os.mkdir(str(self.audios_dir))

    async def start(self) -> None:
        if self._started:
            return

        async with self._lock:
            if self._started:
                return
            async with self.engine.begin() as conn:
                await conn.run_sync(
                    SQLModel.metadata.create_all,
                    tables=[
                        SQLModel.metadata.tables[t.__tablename__] for t in (Record,)  # type: ignore[index]
                    ],
                    checkfirst=True,
                )
                self._started = True

    @asynccontextmanager
    async def session(
        self, auto_flush: bool = False
    ) -> AsyncGenerator[AsyncSession, None]:
        if not self._started:
            raise RuntimeError(f"{self} has not start engine")

        async with AsyncSession(self.engine, autoflush=auto_flush) as session:
            async with session.begin():
                yield session
