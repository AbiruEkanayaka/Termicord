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

@bot.event
async def on_ready():
    try:
        await bot.load_extension("commands.addhost")
        await bot.load_extension("commands.execute")
        await tree.sync()  # Sync slash commands
        print(f"Loaded and Synced all commands!")
        bot.db = await create_db_pool()  # Create the database connection pool
        print(f"Connected to database!")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')

bot.run(TOKEN)