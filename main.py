import nextcord
from nextcord.ext import commands, tasks
import os
from dotenv import load_dotenv
import flask
from threading import Thread
import asyncio

load_dotenv()

# Config
BOT_TOKEN = os.getenv('BOT_TOKEN')
VOICE_CHANNEL_ID = 1470597286269550592
WELCOME_CHANNEL_ID = 1470597378116681812
ALLOWED_ROLE_IDS = [1470596832794251408, 1470596825575854223, 1470596818298601567]
GUILD_ID = 1470597286269550592  # Assumed from voice ch ID; adjust if needed
EMOJI_BADGE = '<:Welcome0:1484564259395604572><:Welcome1:1484564289309380780><:Welcome2:1484564315888681000><:Welcome3:1484564376995234037>'

intents = nextcord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='>', intents=intents)

def get_ordinal(n):
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"

def get_human_count(guild):
    return len([m for m in guild.members if not m.bot])

@bot.event
async def on_ready():
    print(f'{bot.user} has logged in.')
    try:
        synced = await bot.sync_application_commands(guild=nextcord.Object(id=GUILD_ID))
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(e)
    update_voice_channel.start()

@bot.slash_command(guild_ids=[GUILD_ID], description='Say a message as the bot')
async def say(interaction: nextcord.Interaction, message: str):
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        await interaction.response.defer(ephemeral=True)
        return
    await interaction.response.defer()
    await interaction.channel.send(message)
    await interaction.delete_original_response()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.content.startswith('>say '):
        if not any(role.id in ALLOWED_ROLE_IDS for role in message.author.roles):
            await message.delete()
            return
        content = message.content[5:].strip()
        if content:
            await message.channel.send(content)
        await message.delete()
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    guild = member.guild
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        human_count = get_human_count(guild)
        ordinal = get_ordinal(human_count)
        welcome_msg = f"{EMOJI_BADGE} {member.mention} **Welcome to Liberty County State Roleplay Community. You are our `{human_count}`{ordinal} member.**\n> Thanks for joining and have a wonderful day."
        await channel.send(welcome_msg)

@tasks.loop(seconds=600)  # 10 minutes
async def update_voice_channel():
    guild = bot.get_guild(GUILD_ID)
    if guild:
        voice_ch = guild.get_channel(VOICE_CHANNEL_ID)
        if voice_ch:
            human_count = get_human_count(guild)
            new_name = f"(Members: {human_count})"
            await voice_ch.edit(name=new_name)

def run_flask():
    app = flask.Flask(__name__)
    @app.route('/')
    def home():
        return 'Bot is alive!'
    app.run(port=5000, debug=False)

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    bot.run(BOT_TOKEN)
