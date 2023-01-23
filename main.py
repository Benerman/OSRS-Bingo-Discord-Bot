import discord
from discord.ext import commands, tasks
import requests
import json
import os
import config

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

ROLES = ["Team 1", "Team 2", "Team 3", "Team 4", "Team 5", "Team 6"]

def create_discord_friendly_name(text):
    return text.lower().replace(' ', '-')


def load_sheet(SAMPLE_SPREADSHEET_ID, RANGE="A1:Z100"):
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('sheets', 'v4', credentials=creds)

        # Call the Sheets API
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID, range=RANGE).execute()
        values = result.get('values', [])

        if not values:
            print('No data found.')
            return

        
        for row in values:
            print(row)
        return values

    except HttpError as err:
        print(err)


async def clear_team_roles(message):
    print(f'{message.guild.roles=}')
    roles = [discord.utils.get(message.guild.roles, name=rl) for rl in ROLES]
    print(roles)
    for member in message.guild.members:
        await member.remove_roles(*roles)
    print('Removed Team Roles from All Members')    
    

async def create_channels(message, data):
    if not data:
        await message.channel.send('Sheet output unable to be processed')
        return
    for i, row in enumerate(data):
        if i == 0:
            continue
        d = dict(zip(data[0], row))
        print(d)
        category = discord.utils.get(message.guild.categories, name=d['Category'])
        if not category:
            category = await message.guild.create_category(d['Category'])
        role = discord.utils.get(message.guild.roles, name=d['Category'])
        print(f"{role=}")
        print(category.channels)
        print([ch.name for ch in category.channels])
        if not discord.utils.get(category.channels, name=create_discord_friendly_name(d['Name'])):
            if d['Type'] == 'Text':
                chan = await message.guild.create_text_channel(name=create_discord_friendly_name(d['Name']), category=category, )
            else:
                chan = await message.guild.create_voice_channel(name=create_discord_friendly_name(d['Name']), category=category)
            # category = discord.utils.get(message.guild.categories, name=d['Category'])
            await chan.set_permissions(role, read_messages=True,
                                                      send_messages=True)
            await chan.edit(sync_permissions=True)
        else:
            print(d['Name'])
            existing_channel = discord.utils.get(category.channels, name=create_discord_friendly_name(d['Name']))
            await existing_channel.purge(reason="Resetting Channels")



intents = discord.Intents.default()
intents.message_content = True

class MyClient(discord.Client):
    async def on_ready(self):
        print('Bot is Ready')
        print('We have logged in as {0.user}'.format(client))

    async def on_message(self, message):
        if message.author == client.user:
            return
        print(f'Message from {message.author}: {message.content}')

        if message.content.startswith('/bingo'):
            await message.edit(suppress=True)
            await message.channel.typing()
            if message.content.startswith('/bingo build'):
                link = message.content.split('/bingo build')[-1]
                spreadsheet_id = link.split('https://docs.google.com/spreadsheets/d/')[-1].split("/")[0]
                output = load_sheet(spreadsheet_id)
                await clear_team_roles(message)
                await create_channels(message, output)
                await message.channel.send(f'Completed')


client = MyClient(intents=intents)

client.run(config.DISCORD_BOT_TOKEN)

