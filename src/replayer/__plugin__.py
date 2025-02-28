import asyncio
from typing import cast

from melobot import GenericLogger, PluginPlanner
from melobot.handle import get_event
from melobot.plugin import PluginLifeSpan
from melobot.protocols.onebot.v11 import GroupMessageEvent, on_message

from .msg import MsgDB, SegmentTag
from .process import MessageStore
from .utils import get_id, init_conn

REPLAYER = PluginPlanner("1.0.0")


class DataBases:
    msg_db = MsgDB()


MSG_STORE = MessageStore(DataBases.msg_db)


async def start_db(logger: GenericLogger) -> None:
    await DataBases.msg_db.start()
    logger.info("所有数据库已完成初始化")


@REPLAYER.on(PluginLifeSpan.INITED)
async def prepare(logger: GenericLogger) -> None:
    await init_conn(logger)
    await start_db(logger)


@REPLAYER.use
@on_message(checker=lambda e: isinstance(e, GroupMessageEvent))
async def rec_grp_msg() -> None:
    event = cast(GroupMessageEvent, get_event())
    coro = MSG_STORE.process(
        event.message,
        SegmentTag(
            eid=get_id(),
            mid=event.message_id,
            time=event.time,
            gid=event.group_id,
            uid=event.user_id,
            nickname=event.sender.nickname,
        ),
    )
    asyncio.create_task(coro)
