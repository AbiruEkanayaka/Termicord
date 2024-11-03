import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import tempfile
import os
import paramiko
import io
from config import setup_commands

class AddHostCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.describe(
        hostname="The hostname of the host",
        ip="The IP address of the host",
        username="The username to connect to the host",
        password="The password to connect to the host",
        identification_file="The identification file to connect to the host",
        port="The port to connect to the host"
    )
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
                port = 22

            identification_file_content = None
            if identification_file:
                temp_file_path = os.path.join(tempfile.gettempdir(), identification_file.filename)
                await identification_file.save(temp_file_path)

                with open(temp_file_path, "rb") as f:
                    identification_file_content = f.read().decode('utf-8')

                os.remove(temp_file_path)

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

        await self.run_commands_on_host(ip, username, password, identification_file_content, port, setup_commands)

        await interaction.followup.send(f"Host '{hostname}' added successfully and setup commands executed.")

    async def run_commands_on_host(self, ip, username, password, identification_file_content, port, commands):
        """Run commands on the given host using SSH."""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if identification_file_content:
                key = paramiko.RSAKey(file_obj=io.StringIO(identification_file_content))
                client.connect(hostname=ip, port=port, username=username, pkey=key)
            else:
                client.connect(hostname=ip, port=port, username=username, password=password)

            for command in commands:
                stdin, stdout, stderr = client.exec_command(command)
                output = stdout.read().decode('utf-8')
                error = stderr.read().decode('utf-8')
                if error:
                    pass # If warning this will get triggered so doing nothing for now :)

            client.close()
        except Exception as e:
            print(f"An error occurred while executing commands on '{ip}': {e}")

async def setup(bot):
    await bot.add_cog(AddHostCommand(bot))
