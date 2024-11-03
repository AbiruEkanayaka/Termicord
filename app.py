import discord
from discord.ext import commands
import asyncpg
from config import TOKEN, DB_Host, DB_Name, DB_User, DB_Pass, DB_Port

intents = discord.Intents.default()
intents.message_content = True

async def create_db_pool():
    return await asyncpg.create_pool(database=DB_Name, user=DB_User, password=DB_Pass, host=DB_Host, port=DB_Port)

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
bot.db = None

started = False

@bot.event
async def on_ready():
    global started
    if started == False:
        try:
            bot.db = await create_db_pool()
            print(f"Connected to database!")
            await bot.load_extension("commands.addhost")
            await bot.load_extension("commands.execute")
            await bot.load_extension("commands.removehost")
            await bot.load_extension("commands.kill")
            await bot.load_extension("commands.reboot")
            await bot.load_extension("commands.status")
            await bot.load_extension("commands.liveterminal")
            await bot.load_extension("commands.processes")
            await bot.load_extension("commands.users")
            await bot.load_extension("commands.ip")
            await bot.load_extension("commands.ports")
            await bot.load_extension("commands.edithost")
            await bot.load_extension("commands.listhost")
            await bot.load_extension("commands.help")
            await tree.sync()  # Sync slash commands
            print(f"Loaded and Synced all commands!")
        except Exception as e:
            print(f"Failed to sync slash commands: {e}")
        started = True
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')

bot.run(TOKEN)