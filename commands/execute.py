import discord
from discord.ext import commands
import json
import paramiko
from discord import app_commands
from typing import List 

# Required Intents - Adjust as needed based on what your bot will do
intents = discord.Intents.default()  
intents.message_content = True  # Add this if you need to read message content

# Load existing data from JSON file
with open("database.json", "r") as f:
    database = json.load(f)

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

        # Input validation
        if user_id not in database:
            await interaction.followup.send("You don't have any hosts configured. Use `/add-host` first.")
            return

        if host not in database[user_id]:
            await interaction.followup.send("Host not found. Check your configured hosts.")
            return

        host_data = database[user_id][host]

        try:
            # SSH connection setup
            client = paramiko.SSHClient()  # Create SSH client
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if "identification_file" in host_data:
                client.connect(
                    hostname=host_data["ip"],
                    username=host_data["username"],
                    port=host_data.get("port", 22),
                    key_filename=host_data["identification_file"]
                )
            else:
                client.connect(
                    hostname=host_data["ip"],
                    username=host_data["username"],
                    port=host_data.get("port", 22),
                    password=host_data["password"]
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

    @execute.autocomplete("host")  # Apply the autocomplete decorator
    async def host_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
    
        user_id = str(interaction.user.id)
        if user_id not in database:
            return []  # No hosts for this user

        hosts = database[user_id].keys()
        return [
            app_commands.Choice(name=host, value=host)
            for host in hosts if host.startswith(current) 
        ][:25]  # Limit to 25 suggestions


async def setup(bot):
    await bot.add_cog(ExecuteCommand(bot))