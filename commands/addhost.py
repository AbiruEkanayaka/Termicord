import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from typing import List

class AddHostCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add-host", description="Add a new host")
    async def add_host(
        self,
        interaction: discord.Interaction,
        hostname: str,
        ip: str,
        username: str,
        password: Optional[str] = None,
        identification_file: Optional[discord.Attachment] = None,
        port: Optional[int] = None
    ):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        db = self.bot.db

        async with db.acquire() as conn:
            if password is None and identification_file is None:
                await interaction.followup.send("Please provide either a password or an identification file.")
                return

            if port is None:
                port = 22  # Default port if not provided

            identification_file_content = None
            if identification_file:
                # Read the file content
                with open(identification_file.filename, "rb") as f:
                    identification_file_content = f.read().decode('utf-8')

            try:
                await conn.execute(
                    """INSERT INTO hosts (user_id, hostname, ip, username, password, identification_file, port)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (user_id, hostname) DO UPDATE
                    SET ip = $3, username = $4, password = $5, identification_file = $6, port = $7""",
                    user_id, hostname, ip, username, password, identification_file_content, port
                )
            except Exception as e:
                print(f"An error occurred: {e}")
                await interaction.followup.send(f"An error occurred while adding host '{hostname}'. Please try again later.")
                return

        await interaction.followup.send(f"Host '{hostname}' added successfully.")

async def setup(bot):
    await bot.add_cog(AddHostCommand(bot))