import asyncio
import sys

if sys.version != "win32":
    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

from melobot import Bot, Logger, LogLevel
from melobot.protocols.onebot.v11 import ForwardWebSocketIO, OneBotV11Protocol

if __name__ == "__main__":
    bot = Bot(
        "main",
        logger=Logger("main", LogLevel.INFO, to_dir="../logs", two_stream=True),
    )
    bot.add_protocol(OneBotV11Protocol(ForwardWebSocketIO("ws://127.0.0.1:12359")))
    bot.load_plugin("echo")
    bot.load_plugin("replayer")
    bot.run()
