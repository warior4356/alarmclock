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
            "SELECT timers.timer_id, timers.timer_datetime, timers.timer_info, timers.deleted_by "
            "FROM timers WHERE timers.timer_datetime > %s"
        )
        cursor.execute(select_query, (datetime.now(timezone.utc) - timedelta(minutes=58),))
        rows = cursor.fetchall()
        list_text =  "```Timer ID | Date and Time       | Countdown              | Information \n"
        list_text += "------------------------------------------------------------------------\n"
        if len(rows):
            for row in rows:
                if row[3] == 0:
                    diff = row[1] - datetime.now(timezone.utc)
                    print(diff.seconds)
                    print(diff.days)
                    if diff.seconds < cfg.first_interval and row[0] not in first_warning:
                        await alert_channel.send("{0} in {1} minutes!".format(row[2], int(cfg.first_interval/60)))
                        first_warning.append(row[0])
                    if diff.seconds < cfg.second_interval and row[0] not in second_warning:
                        await alert_channel.send("{0} in {1} minutes!".format(row[2], int(cfg.second_interval/60)))
                        second_warning.append(row[0])
                    if diff.days < 0 and row[0] not in final_warning:
                        await alert_channel.send("{0} NOW!".format(row[2]))
                        final_warning.append(row[0])

                    hours = math.floor(diff.days * 24 + diff.seconds/3600)
                    hours = max(min(hours, 999), 0)
                    minutes = math.floor(diff.days*1440 + diff.seconds/60)
                    if minutes > 0:
                        minutes = math.floor(minutes % 60)
                    list_text += "{0}   | {1} | {2:03} Hours, {3:03} Minutes | {4}\n".format(
                        row[0], row[1].astimezone(utc).replace(tzinfo=None), hours, minutes,  row[2])

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
        "INSERT INTO timers (created_by, timer_id, timer_info, timer_datetime, deleted_by) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;"
    )
    cursor.execute(insert_query, (created_by, timer_id, info, time, 0,))

    return timer_id

async def remove_timer(id, deleted_by):
    update_query = (
        "UPDATE timers SET deleted_by = %s WHERE timer_id = %s;"
    )
    cursor.execute(update_query, (deleted_by, id,))

@client.event
async def on_message(message):
    if message.content.startswith('!add'):
        parts = message.content.split(' ', 2)
        if len(parts) != 3:
            await message.channel.send("The correct command is:\n"
                                       "!add yyyy-mm-dd-HH:MM [timer info]")
            return

        try:
            timer = datetime.strptime(parts[1], '%Y-%m-%d-%H:%M')
            timer = timer.replace(tzinfo=utc)
        except ValueError:
            timer = None
        if not timer:
            await message.channel.send("Please format the time as yyyy-mm-dd-HH:MM")
            return

        timer_id = await add_timer(timer, parts[2], message.author.id)
        reply = "Timer {0} created!".format(timer_id)
        await message.channel.send(reply)

    elif message.content.startswith('!rm'):
        parts = message.content.split(' ', 1)
        if len(parts) != 2:
            await message.channel.send("The correct command is:\n"
                                       "!rm [id]")
            return

        await remove_timer(parts[1], message.author.id)
        reply = "Timer {0} removed!".format(parts[1])
        await message.channel.send(reply)

client.loop.create_task(check_timers())
client.run(token)
