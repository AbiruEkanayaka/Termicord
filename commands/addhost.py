import discord
from discord.ext import commands
import json
from discord import app_commands
from typing import Optional
import os

# Load existing data from JSON file
with open("database.json", "r") as f:
    database = json.load(f)

class AddHostCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add-host", description="Add a new host")
    async def add_host(self, interaction: discord.Interaction, hostname: str, ip: str, username: str, password: Optional[str] = None, identification_file: Optional[discord.Attachment] = None, port: Optional[int] = None):
        await interaction.response.defer()
        user_id = str(interaction.user.id)

        # Check if user has provided either a password or a port
        if password is None and identification_file is None:
            await interaction.followup.send("Please provide either a password or an identification file.")
            return

        # Check if the user already exists in the database
        if user_id not in database:
            database[user_id] = {}

        # Add host details under the user's ID
        database[user_id][hostname] = {
            "ip": ip,
            "username": username
        }

        if password is not None:
            database[user_id][hostname]["password"] = password

        if identification_file is not None:
            # Save the identification file to IF folder
            if not os.path.exists("IF"):
                os.mkdir("IF")
            await identification_file.save(f"IF/{user_id}_{hostname}.pem")

            database[user_id][hostname]["identification_file"] = f"IF/{user_id}_{hostname}.pem"

        if port is not None:
            database[user_id][hostname]["port"] = port

        # Save updated database to JSON file
        with open("database.json", "w") as f:
            json.dump(database, f, indent=4)

        await interaction.followup.send(f"Host '{hostname}' added successfully.")

async def setup(bot):
    await bot.add_cog(AddHostCommand(bot))