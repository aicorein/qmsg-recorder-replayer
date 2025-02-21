from __future__ import annotations

import asyncio
import sqlite3
from typing import Any, Callable, Coroutine, Iterable, cast

from melobot.bot import get_bot
from melobot.log import GenericLogger, LogLevel, get_logger
from melobot.protocols.onebot.v11 import Adapter, EchoRequireCtx, Segment
from melobot.protocols.onebot.v11.adapter import segment as se
from melobot.utils import unfold_ctx

from .msg import MsgDB, Record, SegmentHandle, SegmentTag
from .utils import (
    AudioManager,
    FaceTextSegment,
    ImageManager,
    MFaceManager,
    MfaceSegment,
    VideoManager,
    get_id,
    make_record,
)


class MessageStore:
    def __init__(self, db: MsgDB) -> None:
        self.db = db
        self.image_manager = ImageManager(self.db.imgs_dir)
        self.audio_manager = AudioManager(self.db.audios_dir)
        self.video_manager = VideoManager(self.db.videos_dir)
        self.mface_manager = MFaceManager(self.db.mface_dir)
        self.adapter = cast(Adapter, get_bot().get_adapter(Adapter))
        assert self.adapter is not None, "初始化消息段存储器时，无法获取到 ob11 适配器"

    @property
    def logger(self) -> GenericLogger:
        return get_logger()

    async def process(self, segs: list[Segment], tag: SegmentTag, depth: int = 0) -> None:
        if depth > 10:
            raise ValueError(f"递归深度过深，放弃以下消息段的存储：{segs}")

        try:
            new_segs = SegmentNormalizer.process(segs)
            rec_ts: list[asyncio.Task[Record]] = []
            for idx, seg in enumerate(new_segs):
                handle = SegmentHandle(
                    eid=tag.eid,
                    mid=tag.mid,
                    time=tag.time,
                    gid=tag.gid,
                    uid=tag.uid,
                    nickname=tag.nickname,
                    seg=seg,
                    idx=idx,
                )
                handler = cast(
                    Callable[[SegmentHandle, int], Coroutine[Any, Any, Record]] | None,
                    getattr(self, f"{seg.type}_handler", None),
                )
                if handler:
                    rec_ts.append(asyncio.create_task(handler(handle, depth)))
                else:
                    rec_ts.append(asyncio.create_task(self.handler(handle, depth)))

            if len(rec_ts):
                dones, _ = await asyncio.wait(rec_ts)
                await self.commit((t.result() for t in dones))
                if depth > 0:
                    self.logger.debug(f"进入存储过程的 {depth} 次递归")
                self.logger.debug(
                    f"事件 {tag.eid} 已完成存储，消息段类型：[{', '.join((s.type for s in segs))}]"
                )

        except Exception:
            self.logger.exception("存储消息段时出现异常")
            self.logger.generic_obj(
                "异常点局部变量",
                {"tag": tag, "segs": segs, "depth": depth},
                level=LogLevel.ERROR,
            )

    async def commit(self, recs: Iterable[Record]) -> None:
        async with self.db.session() as session:
            try:
                session.add_all(recs)
                await session.commit()
            except sqlite3.IntegrityError as e:
                self.logger.warning(f"出现完整性错误，具体信息：{e}")

    async def text_handler(self, handle: SegmentHandle, _: int) -> Record:
        return make_record(handle, handle.seg.type, text=handle.seg.data["text"])

    async def facetxt_handler(self, handle: SegmentHandle, _: int) -> Record:
        return make_record(
            handle,
            handle.seg.type,
            text=handle.seg.data["text"],
            data=repr(handle.seg.data),
        )

    async def image_handler(self, handle: SegmentHandle, _: int) -> Record:
        seg = cast(se.ImageRecvSegment, handle.seg)
        md5 = await self.image_manager.store(seg.data["url"], handle.time)
        return make_record(handle, seg.type, data=md5)

    async def record_handler(self, handle: SegmentHandle, _: int) -> Record:
        """注意这是语音消息段的处理方法，名称中的 record 与 Record 无关"""
        seg = cast(se.RecordRecvSegment, handle.seg)
        md5 = await self.audio_manager.store(seg.data["url"], handle.time)
        return make_record(handle, seg.type, data=md5)

    async def video_handler(self, handle: SegmentHandle, _: int) -> Record:
        seg = cast(se.VideoRecvSegment, handle.seg)
        md5 = await self.video_manager.store(seg.data["url"], handle.time)
        return make_record(handle, seg.type, data=md5)

    async def at_handler(self, handle: SegmentHandle, _: int) -> Record:
        return make_record(handle, handle.seg.type, data=repr(handle.seg.data))

    async def reply_handler(self, handle: SegmentHandle, _: int) -> Record:
        seg = cast(se.ReplySegment, handle.seg)
        return make_record(handle, seg.type, data=seg.data["id"])

    @unfold_ctx(lambda: EchoRequireCtx().unfold(True))
    async def forward_handler(self, handle: SegmentHandle, depth: int) -> Record:
        seg = cast(se.ForwardSegment, handle.seg)
        hs = await self.adapter.get_forward_msg(seg.data["id"])
        echo = await hs[0]
        assert echo is not None

        data = echo.data
        if data is None:
            self.logger.warning(f"转发消息 {seg.data['id']} 获取失败，放弃后续的递归存储")
            return make_record(handle, seg.type)

        msgs = data["message"]
        ts: list[asyncio.Task[None]] = []
        eids: list[int] = []
        for node_seg in msgs:
            eid = get_id()
            tag = SegmentTag(
                eid=eid,
                mid=None,
                time=None,
                gid=None,
                uid=node_seg.data["user_id"],  # type: ignore
                nickname=node_seg.data["nickname"],  # type: ignore
            )
            eids.append(eid)
            coro = self.process(node_seg.data["content"], tag, depth + 1)  # type: ignore[typeddict-item]
            ts.append(asyncio.create_task(coro))
        if len(ts):
            await asyncio.wait(ts)
        return make_record(handle, seg.type, data=repr(eids))

    async def mface_handler(self, handle: SegmentHandle, _: int) -> Record:
        seg = cast(MfaceSegment, handle.seg)  # type: ignore
        md5 = await self.mface_manager.store(seg.data["url"], handle.time)
        return make_record(handle, handle.seg.type, data=md5)

    async def handler(self, handle: SegmentHandle, depth: int) -> Record:
        return make_record(handle, handle.seg.type, data=handle.seg.to_json())


class SegmentNormalizer:
    @classmethod
    def _join_face_text(self, segs: list[Segment]) -> FaceTextSegment | se.TextSegment:  # type: ignore
        if len(segs) == 1 and isinstance(segs[0], se.TextSegment):
            return segs[0]
        if all(isinstance(s, se.TextSegment) for s in segs):
            return se.TextSegment("".join(s.data["text"] for s in segs))

        text_list: list[str] = []
        face_list: list[int] = []
        for seg in segs:
            if isinstance(seg, se.FaceSegment):
                text_list.append("\u0000")
                face_list.append(seg.data["id"])
            else:
                text_list.append(
                    cast(se.TextSegment, seg).data["text"].replace("\u0000", "")
                )
        return FaceTextSegment(text="".join(text_list), faces=repr(face_list))  # type: ignore

    @classmethod
    def gen_face_text(self, segs: list[Segment]) -> list[Segment]:
        start, end = -1, -1
        new_segs: list[Segment] = []
        for idx, seg in enumerate(segs):
            if isinstance(seg, (se.FaceSegment, se.TextSegment)):
                if start == -1:
                    start = idx
                else:
                    end = idx
            else:
                if start != -1:
                    if end == -1:
                        end = start
                    new_segs.append(self._join_face_text(segs[start : end + 1]))
                    start, end = -1, -1
                new_segs.append(seg)

        if start != -1:
            if end == -1:
                end = start
            new_segs.append(self._join_face_text(segs[start : end + 1]))
        return new_segs

    @classmethod
    def process(self, segs: list[Segment]) -> list[Segment]:
        new_segs = self.gen_face_text(segs)
        return new_segs
