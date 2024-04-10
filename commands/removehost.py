import discord
from discord.ext import commands
from discord import app_commands
from typing import List

class RemoveHostCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.describe(hostname="The hostname of the host to remove")
    @app_commands.command(name="remove-host", description="Remove an existing host")
    async def remove_host(
        self,
        interaction: discord.Interaction,
        hostname: str
    ):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        db = self.bot.db

        async with db.acquire() as conn:
            try:
                result = await conn.execute(
                    """DELETE FROM hosts WHERE user_id = $1 AND hostname = $2""",
                    user_id, hostname
                )
                if result == 'DELETE 0':
                    await interaction.followup.send(f"Host '{hostname}' not found.")
                else:
                    await interaction.followup.send(f"Host '{hostname}' removed successfully.")
            except Exception as e:
                print(f"An error occurred: {e}")
                await interaction.followup.send(f"An error occurred while removing host '{hostname}'. Please try again later.")
    
    @remove_host.autocomplete("hostname")
    async def host_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        user_id = str(interaction.user.id)
        db = self.bot.db

        async with db.acquire() as conn:
            try:
                hosts = await conn.fetch(
                    "SELECT hostname FROM hosts WHERE user_id = $1 AND hostname LIKE $2",
                    user_id, f"{current}%"
                )
            except Exception as e:
                print(f"An error occurred: {e}")
                return []

            return [
                app_commands.Choice(name=host["hostname"], value=host["hostname"])
                for host in hosts
            ][:25]

async def setup(bot):
    await bot.add_cog(RemoveHostCommand(bot))