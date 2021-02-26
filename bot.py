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

    timers_message = None
    ops_message = None
    list_channel = client.get_channel(cfg.list_channel)
    alert_channel = client.get_channel(cfg.alert_channel)

    first_warning = []
    second_warning = []
    final_warning = []

    while True:
        select_query = (
            "SELECT timers.timer_id, timers.timer_datetime, timers.timer_info, timers.timer_fc, timers.deleted_by "
            "FROM timers WHERE timers.timer_datetime > %s ORDER BY timers.timer_datetime DESC"
        )
        cursor.execute(select_query, (datetime.now(timezone.utc) - timedelta(minutes=30),))
        rows = cursor.fetchall()
        timers_text = "```md\n"
        timers_text += "Timer ID | Date and Time    | Countdown         | Fleet Commander    | Information \n"
        timers_text += "-----------------------------------------------------------------------------------------------\n"
        ops_text = "```md\n"
        ops_text += "Op ID    | Date and Time    | Countdown         | Fleet Commander    | Information \n"
        ops_text += "-----------------------------------------------------------------------------------------------\n"
        if len(rows):
            for row in rows:
                if row[4] == 0:
                    diff = row[1] - datetime.now(timezone.utc)
                    hours = math.floor(diff.total_seconds()/3600)
                    hours = max(min(hours, 99), 0)
                    minutes = math.floor(diff.total_seconds()/60)

                    if minutes > 0:
                        minutes = math.floor(minutes % 60)

                    countdown = "        {0:02}h {1:03}m ".format(hours, minutes)
                    if diff.total_seconds() < cfg.first_interval:
                        countdown = "[ALERT]({0:02}h {1:03}m)".format(hours, minutes)

                    if row[3]:
                        try:
                            fc = await list_channel.guild.fetch_member(row[3])
                            ops_text += "{0}   | {1} | {2} | {3:18.18} | {4}\n".format(
                                row[0], row[1].strftime("%Y-%m-%d %H:%M"), countdown, fc.display_name, row[2])
                        except:
                            ops_text += "{0}   | {1} | {2} | {3:18.18} | {4}\n".format(
                                row[0], row[1].strftime("%Y-%m-%d %H:%M"), countdown, "Complain To Kat", row[2])



                        if diff.total_seconds() < cfg.first_interval and row[0] not in first_warning:
                            await alert_channel.send("`{0} in {1} minutes!` <@{2}>".format(row[2], int(
                                cfg.first_interval / 60), row[3]))
                            first_warning.append(row[0])
                        if diff.total_seconds() < cfg.second_interval and row[0] not in second_warning:
                            await alert_channel.send("`{0} in {1} minutes!` <@{2}>".format(row[2], int(
                                cfg.second_interval / 60), row[3]))
                            second_warning.append(row[0])
                        if diff.total_seconds() < 0 and row[0] not in final_warning:
                            await alert_channel.send("`{0} NOW!` <@{1}>".format(row[2], row[3]))
                            final_warning.append(row[0])
                    else:
                        timers_text += "{0}   | {1} | {2} | {3:18.18} | {4}\n".format(
                            row[0], row[1].strftime("%Y-%m-%d %H:%M"), countdown, "Needed", row[2])

                        if diff.total_seconds() < cfg.first_interval and row[0] not in first_warning:
                            await alert_channel.send("`{0} in {1} minutes with no FC!`".format(row[2], int(
                                cfg.first_interval / 60)))
                            first_warning.append(row[0])
                        if diff.total_seconds() < cfg.second_interval and row[0] not in second_warning:
                            await alert_channel.send("`{0} in {1} minutes with no FC!`>".format(row[2], int(
                                cfg.second_interval / 60)))
                            second_warning.append(row[0])
                        if diff.total_seconds() < 0 and row[0] not in final_warning:
                            await alert_channel.send("`{0} NOW with no FC!`>".format(row[2]))
                            final_warning.append(row[0])

        timers_text += "```"
        ops_text += "```"

        if not timers_message:
            timers_message = await list_channel.send(timers_text)
        else:
            await timers_message.edit(content=timers_text)

        if not ops_message:
            ops_message = await list_channel.send(ops_text)
        else:
            await ops_message.edit(content=ops_text)
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

    info = await clean_string(info)

    insert_query = (
        "INSERT INTO timers (created_by, timer_id, timer_info, timer_datetime, deleted_by, timer_fc) "
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;"
    )
    cursor.execute(insert_query, (created_by, timer_id, info, time, 0, None,))

    return timer_id

async def add_op(time, info, created_by):
    check_query = (
        "SELECT EXISTS(SELECT 1 FROM timers WHERE timer_id=%s)"
    )

    unique = False

    while not unique :
        timer_id = random.randint(100000, 999999)
        if not cursor.execute(check_query, (timer_id,)):
            unique = True

    info = await clean_string(info)

    insert_query = (
        "INSERT INTO timers (created_by, timer_id, timer_info, timer_datetime, deleted_by, timer_fc) "
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;"
    )
    cursor.execute(insert_query, (created_by, timer_id, info, time, 0, created_by,))

    return timer_id

async def update_fc(timer_id, fc_name, edited_by):
    update_query = (
        "UPDATE timers SET timer_fc = %s, edited_by = %s WHERE timer_id = %s;"
    )
    cursor.execute(update_query, (fc_name, edited_by, timer_id,))

async def update_info(timer_id, info, edited_by):
    info = await clean_string(info)
    update_query = (
        "UPDATE timers SET timer_info = %s, edited_by = %s WHERE timer_id = %s;"
    )
    cursor.execute(update_query, (info, edited_by, timer_id,))

async def update_time(timer_id, new_time, edited_by):
    update_query = (
        "UPDATE timers SET timer_datetime = %s, edited_by = %s WHERE timer_id = %s;"
    )
    cursor.execute(update_query, (new_time, edited_by, timer_id,))


async def remove_timer(timer_id, deleted_by):
    update_query = (
        "UPDATE timers SET deleted_by = %s WHERE timer_id = %s;"
    )
    cursor.execute(update_query, (deleted_by, timer_id,))

def calcdatetime(date: str):
    try:
        timer = datetime.strptime(date, '%Y-%m-%dT%H:%M')
        timer = timer.replace(tzinfo=utc)
    except ValueError:
        timer = None
    if not timer:
        clean_date = date.lower()
        days = clean_date.split("d", 1)
        hours = days[1].split("h", 1)
        minutes = hours[1].split("m", 1)
        timer = datetime.now(timezone.utc) + timedelta(
            days=int(days[0]), hours=int(hours[0]), minutes=int(minutes[0])
        )

    return timer

async def clean_string(string):
    new_string = ''
    new_string = new_string.join(ch for ch in string if ch.isalnum() or ch == '-' or ch == ' ')
    return new_string

@client.event
async def on_message(message):
    if message.channel.id not in cfg.channel_whitelist:
        return

    if message.content.startswith('!ac'):
        if message.content.startswith('!ac timer'):
            parts = message.content.split(' ', 3)
            if len(parts) != 4:
                await message.channel.send("The correct command is:\n"
                                           "!ac add [XXdYYhZZm or yyyy-mm-ddTHH:MM] [timer info]")
                return

            timer = calcdatetime(parts[2])

            if timer < datetime.now(timezone.utc):
                await message.channel.send("Please try again or invent time travel.")
                return

            timer_id = await add_timer(timer, parts[3], message.author.id)
            reply = "Timer {0} scheduled at {1}!".format(timer_id, timer.strftime("%Y-%m-%d %H:%M"))
            await message.channel.send(reply)

        elif message.content.startswith('!ac op'):
            parts = message.content.split(' ', 3)
            if len(parts) != 4:
                await message.channel.send("The correct command is:\n"
                                           "!ac add [XXdYYhZZm or yyyy-mm-ddTHH:MM] [timer info]")
                return

            timer = calcdatetime(parts[2])

            if timer < datetime.now(timezone.utc):
                await message.channel.send("Please try again or invent time travel.")
                return

            timer_id = await add_timer(timer, parts[3], message.author.id)
            reply = "Op {0} scheduled at {1}!".format(timer_id, timer.strftime("%Y-%m-%d %H:%M"))
            await message.channel.send(reply)

        elif message.content.startswith('!ac rm'):
            parts = message.content.split(' ', 2)
            if len(parts) != 3:
                await message.channel.send("The correct command is:\n"
                                           "!ac rm [id]")
                return

            await remove_timer(parts[2], message.author.id)
            reply = "Timer/op {0} removed!".format(parts[2])
            await message.channel.send(reply)

        elif message.content.startswith('!ac edit'):
            parts = message.content.split(' ', 3)
            if len(parts) != 4:
                await message.channel.send("The correct command is:\n"
                                           "!ac edit [id] [new info]")
                return

            await update_info(parts[2], parts[3], message.author.id)
            reply = "Timer/op {0} updated!".format(parts[2])
            await message.channel.send(reply)

        elif message.content.startswith('!ac take'):
            parts = message.content.split(' ', 3)
            if len(parts) != 3:
                await message.channel.send("The correct command is:\n"
                                           "!ac take [id]")
                return

            fc = await message.guild.fetch_member(message.author.id)

            await update_fc(parts[2], message.author.id, message.author.id)
            reply = "Timer/op {0} assigned to {1}!".format(parts[2], fc.display_name)
            await message.channel.send(reply)

        elif message.content.startswith('!ac release'):
            parts = message.content.split(' ', 3)
            if len(parts) != 3:
                await message.channel.send("The correct command is:\n"
                                           "!ac release [id]")
                return

            fc = await message.guild.fetch_member(message.author.id)

            await update_fc(parts[2], None, message.author.id)
            reply = "Op {0} returned to timer board!".format(parts[2])
            await message.channel.send(reply)

        elif message.content.startswith('!ac mv'):
            parts = message.content.split(' ', 3)
            if len(parts) != 4:
                await message.channel.send("The correct command is:\n"
                                           "!ac mv [id] [new time]")
                return

            timer = calcdatetime(parts[3])

            if timer < datetime.now(timezone.utc):
                await message.channel.send("Please try again or invent time travel.")
                return

            await update_time(parts[2], timer, message.author.id)
            reply = "Timer/op {0} updated to {1}!".format(parts[2], timer.strftime("%Y-%m-%d %H:%M"))
            await message.channel.send(reply)

        else:
            await message.channel.send("AlarmClock Commands:\n"
                                       "!ac timer [XXdYYhZZm or yyyy-mm-ddTHH:MM] [timer info] - Adds a new timer\n"
                                       "!ac op [XXdYYhZZm or yyyy-mm-ddTHH:MM] [op info] - Adds a new op with you as FC\n"
                                       "!ac rm [id] - Removes an existing timer/op\n"
                                       "!ac edit [id] [new info] - Updates the information on an existing timer/op\n"
                                       "!ac mv [id] [new time] - Updates the time on an existing timer/op\n"
                                       "!ac take [id] - Makes a timer/op into an op for you\n"
                                       "!ac release [id] - Returns an op to the timer board")

client.loop.create_task(check_timers())
client.run(token)
