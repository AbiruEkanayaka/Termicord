import discord
from discord.ext import commands
from discord import app_commands

class ListHostsCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="list-hosts", description="List all added hosts")
    async def list_hosts(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        db = self.bot.db
        
        async with db.acquire() as conn:
            hosts = await conn.fetch("SELECT hostname, ip, username, port FROM hosts WHERE user_id = $1", user_id)

        if not hosts:
            await interaction.followup.send("You have no hosts added.")
            return
        
        embed = discord.Embed(
            title="Your Hosts",
            description="Here are your added hosts:",
            color=discord.Color.blue()
        )

        for host in hosts:
            embed.add_field(
                name=f"🔧 {host['hostname']}",
                value=f"**IP:** {host['ip']}\n**Username:** {host['username']}\n**Port:** {host['port']}",
                inline=False
            )

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ListHostsCommand(bot))
