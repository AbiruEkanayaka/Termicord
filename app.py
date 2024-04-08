import discord
from discord.ext import commands
from config import TOKEN

intents = discord.Intents.default()  
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree  

@bot.event
async def on_ready():
    try:
        await bot.load_extension("commands.addhost")
        await bot.load_extension("commands.execute")
        await tree.sync()  # Sync slash commands
        print(f"Loaded and Synced all commands!") 
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')


bot.run(TOKEN)