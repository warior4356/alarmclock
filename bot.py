from discord import Client, utils, member
import cfg
import database
from datetime import datetime
from datetime import timezone
from datetime import timedelta
from random import randint
import asyncio
import re
import random
import math
import os
import pytz

connection = database.create_connection(
    "alarmclock", "postgres", cfg.db_password, "127.0.0.1", "5432"
)
connection.autocommit = True
cursor = connection.cursor()

client = Client()
polling_interval = cfg.polling_interval
token = cfg.token
random.seed()

utc = pytz.timezone('UTC')

async def check_timers():
    await client.wait_until_ready()

    list_message = None
    list_channel = client.get_channel(cfg.list_channel)
    alert_channel = client.get_channel(cfg.alert_channel)

    first_warning = []
    second_warning = []
    final_warning = []

    while True:
        select_query = (
            "SELECT timers.timer_id, timers.timer_datetime, timers.timer_info, timers.timer_fc, timers.deleted_by "
            "FROM timers WHERE timers.timer_datetime > %s"
        )
        cursor.execute(select_query, (datetime.now(timezone.utc) - timedelta(minutes=30),))
        rows = cursor.fetchall()
        list_text = "```md\n"
        list_text += "Timer ID | Date and Time    | Countdown         | Fleet Commander    | Information \n"
        list_text += "-----------------------------------------------------------------------------------------------\n"
        if len(rows):
            for row in rows:
                if row[4] == 0:
                    diff = row[1] - datetime.now(timezone.utc)

                    if diff.seconds < cfg.first_interval and row[0] not in first_warning:
                        await alert_channel.send("`{0} in {1} minutes!`".format(row[2], int(cfg.first_interval/60)))
                        first_warning.append(row[0])
                    if diff.seconds < cfg.second_interval and row[0] not in second_warning:
                        await alert_channel.send("`{0} in {1} minutes!`".format(row[2], int(cfg.second_interval/60)))
                        second_warning.append(row[0])
                    if diff.days < 0 and row[0] not in final_warning:
                        await alert_channel.send("`{0} NOW!`".format(row[2]))
                        final_warning.append(row[0])

                    hours = math.floor(diff.days * 24 + diff.seconds/3600)
                    hours = max(min(hours, 99), 0)
                    minutes = math.floor(diff.days*1440 + diff.seconds/60)

                    if minutes > 0:
                        minutes = math.floor(minutes % 60)

                    countdown = "        {0:02}h {1:03}m ".format(hours, minutes)
                    if diff.seconds < cfg.first_interval or diff.days < 0:
                        countdown = "[ALERT]({0:02}h {1:03}m)".format(hours, minutes)

                    list_text += "{0}   | {1} | {2} | {3:18.18} | {4}\n".format(
                        row[0], row[1].strftime("%Y-%m-%d %H:%M"), countdown, row[3], row[2])

            list_text += "```"

            if not list_message:
                list_message = await list_channel.send(list_text)
            else:
                await list_message.edit(content=list_text)
        await asyncio.sleep(cfg.polling_interval)

async def add_timer(time, info, created_by):
    check_query = (
        "SELECT EXISTS(SELECT 1 FROM timers WHERE timer_id=%s)"
    )

    unique = False

    while not unique :
        timer_id = random.randint(100000, 999999)
        if not cursor.execute(check_query, (timer_id,)):
            unique = True

    insert_query = (
        "INSERT INTO timers (created_by, timer_id, timer_info, timer_datetime, deleted_by, timer_fc) "
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;"
    )
    cursor.execute(insert_query, (created_by, timer_id, info, time, 0, "Needed",))

    return timer_id

async def update_fc(timer_id, fc_name):
    update_query = (
        "UPDATE timers SET timer_fc = %s WHERE timer_id = %s;"
    )
    cursor.execute(update_query, (fc_name, timer_id,))

async def update_info(timer_id, info):
    update_query = (
        "UPDATE timers SET timer_info = %s WHERE timer_id = %s;"
    )
    cursor.execute(update_query, (info, timer_id,))

async def update_time(timer_id, new_time):
    update_query = (
        "UPDATE timers SET timer_datetime = %s WHERE timer_id = %s;"
    )
    cursor.execute(update_query, (new_time, timer_id,))


async def remove_timer(timer_id, deleted_by):
    update_query = (
        "UPDATE timers SET deleted_by = %s WHERE timer_id = %s;"
    )
    cursor.execute(update_query, (deleted_by, timer_id,))

def calcdatetime(date: str):
    clean_date = date.lower()
    days = clean_date.split("d", 1)
    hours = days[1].split("h", 1)
    minutes = hours[1].split("m", 1)
    event_date = datetime.now(timezone.utc) + timedelta(
        days=int(days[0]), hours=int(hours[0]), minutes=int(minutes[0])
    )

    return event_date

@client.event
async def on_message(message):
    if message.content.startswith('!ac'):
        if message.content.startswith('!ac add'):
            parts = message.content.split(' ', 3)
            if len(parts) != 4:
                await message.channel.send("The correct command is:\n"
                                           "!ac add XXdYYhZZm [timer info]")
                return

            timer = calcdatetime(parts[2])

            if timer < datetime.now(timezone.utc):
                await message.channel.send("Please format the time as XXdYYhZZm")
                return

            timer_id = await add_timer(timer, parts[3], message.author.id)
            reply = "Timer {0} created!".format(timer_id)
            await message.channel.send(reply)

        elif message.content.startswith('!ac rm'):
            parts = message.content.split(' ', 2)
            if len(parts) != 3:
                await message.channel.send("The correct command is:\n"
                                           "!ac rm [id]")
                return

            await remove_timer(parts[2], message.author.id)
            reply = "Timer {0} removed!".format(parts[2])
            await message.channel.send(reply)

        elif message.content.startswith('!ac edit'):
            parts = message.content.split(' ', 3)
            if len(parts) != 4:
                await message.channel.send("The correct command is:\n"
                                           "!ac edit [id] [new info]")
                return

            await update_info(parts[2], parts[3])
            reply = "Timer {0} updated!".format(parts[2])
            await message.channel.send(reply)

        elif message.content.startswith('!ac assign'):
            parts = message.content.split(' ', 3)
            if len(parts) != 4:
                await message.channel.send("The correct command is:\n"
                                           "!ac assign [id] [fc name]")
                return

            await update_fc(parts[2], parts[3])
            reply = "Timer {0} assigned to {1}!".format(parts[2], parts[3])
            await message.channel.send(reply)

        elif message.content.startswith('!ac reschedule'):
            parts = message.content.split(' ', 3)
            if len(parts) != 4:
                await message.channel.send("The correct command is:\n"
                                           "!ac reschedule [id] [new time]")
                return

            timer = calcdatetime(parts[3])

            if timer < datetime.now(timezone.utc):
                await message.channel.send("Please format the time as XXdYYhZZm")
                return

            await update_time(parts[2], timer)
            reply = "Timer {0} updated to {1}!".format(parts[2], timer)
            await message.channel.send(reply)

        else:
            await message.channel.send("AlarmClock Commands:\n"
                                       "!ac add XXdYYhZZm [timer info] - Adds a new timer\n"
                                       "!ac rm [id] - Removes an existing timer\n"
                                       "!ac edit [id] [new info] - Updates the information on an existing timer\n"
                                       "!ac assign [id] [fc name] - Updates the FC on an existing timer\n"
                                       "!ac reschedule [id] [new time] - Updates the time on an existing timer")

client.loop.create_task(check_timers())
client.run(token)
