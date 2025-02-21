import datetime as dt
import time

from melobot import MetaInfo, PluginPlanner, on_start_match, send_text

ECHO = PluginPlanner("1.0.0")


START_MOMENT = time.time()
FMT_START_MOMENT = dt.datetime.now().strftime("%m-%d %H:%M:%S")


def get_alive_time() -> str:
    def format_nums(*time_num: int) -> list[str]:
        return [str(num) if num >= 10 else "0" + str(num) for num in time_num]

    interval = int(time.time() - START_MOMENT)
    days = interval // 3600 // 24
    hours = interval // 3600 % 24
    mins = interval // 60 % 60
    secs = interval % 60
    times = format_nums(days, hours, mins, secs)
    return f"{times[0]}d {times[1]}h {times[2]}m {times[3]}s"


@ECHO.use
@on_start_match(target="ping")
async def ping() -> None:
    await send_text("pong")


@ECHO.use
@on_start_match(target="info")
async def info() -> None:
    await send_text(
        "[Info]\n"
        "Name: QMsg Auto Recorder & Replayer\n"
        "Status: Recording started.\n"
        f"Core: {MetaInfo.name} {MetaInfo.ver}\n"
        f"Start at: {FMT_START_MOMENT}\n"
        f"Alive time: {get_alive_time()}"
    )
