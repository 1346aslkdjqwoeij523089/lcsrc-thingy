import nextcord
from nextcord.ext import commands, tasks
import os
from dotenv import load_dotenv
import flask
import logging
import time
import threading
import asyncio
import signal

load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration with env vars and fallbacks
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable is required!")
    exit(1)

GUILD_ID = int(os.getenv('GUILD_ID', '1289789596238086194'))
VOICE_CHANNEL_ID = int(os.getenv('VOICE_CHANNEL_ID', '1470597286269550592'))  # Confirmed VC
WELCOME_CHANNEL_ID = int(os.getenv('WELCOME_CHANNEL_ID', '1470597378116681812'))
allowed_role_str = os.getenv('ALLOWED_ROLE_IDS', '1470596832794251408,1470596825575854223,1470596818298601567')
ALLOWED_ROLE_IDS = [int(rid.strip()) for rid in allowed_role_str.split(',')]
EMOJI_BADGE = os.getenv('EMOJI_BADGE', '<:Welcome0:1484564259395604572><:Welcome1:1484564289309380780><:Welcome2:1484564315888681000><:Welcome3:1484564376995234037>')

if os.getenv('GUILD_ID') is None:
    logger.warning("Using hardcoded GUILD_ID - set env var for flexibility.")

intents = nextcord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='>', intents=intents)

# Cache for human count
human_cache = {'count': 0, 'timestamp': 0}
CACHE_DURATION = 300  # 5 minutes

def get_human_count(guild):
    import time
    now = time.time()
    if now - human_cache['timestamp'] < CACHE_DURATION:
        return human_cache['count']
    count = len([m for m in guild.members if not m.bot])
    human_cache.update({'count': count, 'timestamp': now})
    return count

def get_ordinal(n):
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"

@bot.event
async def on_ready():
    logger.info(f'{bot.user} (ID: {bot.user.id}) has logged in!')
    logger.info(f'Connected to {len(bot.guilds)} guilds.')
    try:
        synced = await bot.tree.sync(guild=nextcord.Object(id=GUILD_ID))
        logger.info(f'Synced {len(synced)} application command(s)')
    except Exception as e:
        logger.error(f'Application command sync failed: {e}')
    
    # Add slash command error handler after tree ready
    async def on_app_command_error(interaction: nextcord.Interaction, error: nextcord.AppCommandError):
        logger.error(f'Slash command error for {interaction.user}: {error}', exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message('An error occurred while executing the command!', ephemeral=True)
    
    bot.tree.error(on_app_command_error)
    
    # Set visible presence
    activity = nextcord.Activity(
        type=nextcord.ActivityType.watching, 
        name="Liberty County State Roleplay | /say"
    )
    await bot.change_presence(activity=activity, status=nextcord.Status.online)
    update_voice_channel.start()
    logger.info("Bot fully ready and tasks started!")

@bot.event
async def on_error(event: str, *args, **kwargs):
    logger.error(f"On_error triggered for event '{event}':", exc_info=True)

@bot.slash_command(guild_ids=[GUILD_ID], description='Say a message as the bot')
async def say(interaction: nextcord.Interaction, message: str):
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        await interaction.response.send_message("❌ Insufficient permissions!", ephemeral=True)
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
    if channel is not None:
        human_count = get_human_count(guild)
        ordinal = get_ordinal(human_count)
        welcome_msg = f"{EMOJI_BADGE} {member.mention} **Welcome to Liberty County State Roleplay Community. You are our `{human_count}`{ordinal} member.**\n> Thanks for joining and have a wonderful day."
        await channel.send(welcome_msg)

@tasks.loop(seconds=600)  # 10 minutes
async def update_voice_channel():
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    voice_ch = guild.get_channel(VOICE_CHANNEL_ID)
    if voice_ch is None:
        return
    human_count = get_human_count(guild)
    new_name = f"(Members: {human_count})"
    try:
        await voice_ch.edit(name=new_name)
        logger.info(f"Voice channel updated to {new_name}")
    except nextcord.Forbidden:
        logger.warning("Missing permissions to edit voice channel")
    except Exception as e:
        logger.error(f"Voice channel update failed: {e}")

async def bot_main():
    """Main bot runner with retry logic"""
    logger.info("=== Starting LCSRPC Bot ===")
    logger.info(f"Target guild: {GUILD_ID}")
    max_retries = 5
    backoff = 1
    for attempt in range(max_retries):
        try:
            logger.info(f"Bot login attempt {attempt + 1}/{max_retries}")
            await bot.start(BOT_TOKEN)
        except nextcord.LoginFailure as e:
            logger.error(f"Authentication failed: {e}")
            break
        except asyncio.TimeoutError:
            logger.warning("Login timeout, retrying...")
        except nextcord.HTTPException as e:
            if e.status == 429 or 'rate limit' in str(e).lower():
                wait_time = backoff * 5
                logger.warning(f"Rate limited. Waiting {wait_time}s before retry {attempt + 1}")
                backoff *= 2
                await asyncio.sleep(wait_time)
                continue
            logger.error(f"HTTP error during login: {e}")
            break
        except Exception as e:
            logger.exception(f"Unexpected error during bot start: {e}")
            break
        # Success case not reached due to blocking start()
    else:
        logger.error("Max retries exceeded. Bot could not connect.")
    logger.info("Bot main ended.")

def create_app() -> flask.Flask:
    app = flask.Flask(__name__)
    
    @app.route('/')
    def home():
        return {'status': 'alive', 'service': 'LCSRPC Bot + Web'}
    
    @app.route('/bot-status')
    def status():
        global bot_start_time
        uptime = time.time() - (bot_start_time or 0) if 'bot_start_time' in globals() else 0
        is_ready = hasattr(bot, 'is_ready') and bot.is_ready()
        is_logged_in = hasattr(bot, 'is_logged_in') and bot.is_logged_in()
        return {
            'flask_alive': True,
            'bot_ready': is_ready,
            'bot_logged_in': is_logged_in,
            'bot_user': str(bot.user) if is_ready else 'Not ready',
            'guild_count': len(bot.guilds) if hasattr(bot, 'guilds') else 0,
            'uptime_seconds': uptime,
            'cache_human_count': human_cache.get('count', 0)
        }
    
    return app

def run_flask():
    """Run Flask in thread"""
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Starting Flask web server on port {port}")
    app = create_app()
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    global bot_start_time
    bot_start_time = time.time()
    
    logger.info("🎯 Liberty County State Roleplay Bot starting...")
    logger.info(f"Python version: {os.sys.version.split()[0]}")
    
    # Graceful shutdown setup
    def shutdown(sig=None, frame=None):
        logger.info("Shutdown signal received, closing bot...")
        if not bot.is_closed():
            # Run close in event loop if possible
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(bot.close())
            except:
                asyncio.run(bot.close())
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Start Flask in daemon thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Bot runs in main thread (primary process)
    try:
        asyncio.run(bot_main())
    except KeyboardInterrupt:
        shutdown()

