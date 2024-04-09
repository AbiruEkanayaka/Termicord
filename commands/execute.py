import discord
from discord.ext import commands
import asyncpg
import paramiko
from discord import app_commands
import os
from typing import List

class ExecuteCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="execute", description="Execute a bash command on a selected host")
    async def execute(
        self,
        interaction: discord.Interaction,
        command: str,
        host: str
    ):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        db = self.bot.db

        async with db.acquire() as conn:
            try:
                host_data = await conn.fetchrow(
                    "SELECT ip, username, password, identification_file, port FROM hosts WHERE user_id = $1 AND hostname = $2",
                    user_id, host
                )
            except Exception as e:
                print(f"An error occurred: {e}")
                await interaction.followup.send(f"An error occurred while executing command on host '{host}'. Please try again later.")
                return

            if not host_data:
                await interaction.followup.send("Host not found. Check your configured hosts.")
                return

            # Destructure host_data tuple
            ip, username, password, identification_file, port = host_data

            # Temporary file creation
            temp_file_path = f"temp.pem"
            with open(temp_file_path, "w") as temp_file:
                temp_file.write(identification_file)

            try:
                # SSH connection setup
                client = paramiko.SSHClient()  # Create SSH client
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                if identification_file:
                    client.connect(
                        hostname=ip,
                        username=username,
                        port=port or 22,
                        key_filename=temp_file_path
                    )
                else:
                    client.connect(
                        hostname=ip,
                        username=username,
                        password=password,
                        port=port or 22
                    )

                # Command execution
                stdin, stdout, stderr = client.exec_command(command)
                output = stdout.read().decode()
                error = stderr.read().decode()

                # Embed creation
                embed = discord.Embed(title=f"Command Execution on {host}")
                if output:
                    embed.add_field(name="Output", value=f"\n```{output}```\n", inline=False)
                if error:
                    embed.add_field(name="Error", value=f"\n```{error}```\n", inline=False)

                await interaction.followup.send(embed=embed)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}")
            finally:
                client.close()
                # Remove temporary file
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

    @execute.autocomplete("host")
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
    await bot.add_cog(ExecuteCommand(bot))
