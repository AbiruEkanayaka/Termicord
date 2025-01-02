import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import tempfile
import os
import paramiko
import io
import asyncio
from config import setup_commands

class AddHostCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.timeout = 30  # Default timeout in seconds

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

        if password is None and identification_file is None:
            await interaction.followup.send("Please provide either a password or an identification file.")
            return

        if port is None:
            port = 22

        identification_file_content = None
        if identification_file:
            try:
                temp_file_path = os.path.join(tempfile.gettempdir(), identification_file.filename)
                await identification_file.save(temp_file_path)

                with open(temp_file_path, "rb") as f:
                    identification_file_content = f.read().decode('utf-8')

                os.remove(temp_file_path)
            except Exception as e:
                await interaction.followup.send(f"Failed to process identification file: {str(e)}")
                return

        # Test connection before saving
        try:
            connection_test = await asyncio.wait_for(
                self.test_connection(ip, username, password, identification_file_content, port),
                timeout=self.timeout
            )
            if not connection_test[0]:
                await interaction.followup.send(f"Connection test failed: {connection_test[1]}")
                return
        except asyncio.TimeoutError:
            await interaction.followup.send(f"Connection test timed out after {self.timeout} seconds.")
            return
        except Exception as e:
            await interaction.followup.send(f"Connection test failed with error: {str(e)}")
            return

        # Save host to database
        async with db.acquire() as conn:
            try:
                await conn.execute(
                    """INSERT INTO hosts (user_id, hostname, ip, username, password, identification_file, port)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (user_id, hostname) DO UPDATE
                    SET ip = $3, username = $4, password = $5, identification_file = $6, port = $7""",
                    user_id, hostname, ip, username, password, identification_file_content, port
                )
            except Exception as e:
                await interaction.followup.send(f"Failed to save host configuration: {str(e)}")
                return

        # Run setup commands
        try:
            await asyncio.wait_for(
                self.run_commands_on_host(ip, username, password, identification_file_content, port, setup_commands),
                timeout=self.timeout * 2
            )
            await interaction.followup.send(f"Host '{hostname}' added successfully and setup commands executed.")
        except asyncio.TimeoutError:
            await interaction.followup.send(f"Setup commands timed out after {self.timeout * 2} seconds. Host was added but might not be properly configured.")
        except Exception as e:
            await interaction.followup.send(f"Host added but setup commands failed: {str(e)}")

    async def test_connection(self, ip, username, password, identification_file_content, port):
        """Test SSH connection to the host."""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if identification_file_content:
                key = paramiko.RSAKey(file_obj=io.StringIO(identification_file_content))
                client.connect(hostname=ip, port=port, username=username, pkey=key, timeout=10)
            else:
                client.connect(hostname=ip, port=port, username=username, password=password, timeout=10)

            client.close()
            return True, "Connection successful"
        except Exception as e:
            return False, str(e)

    async def run_commands_on_host(self, ip, username, password, identification_file_content, port, commands):
        """Run commands on the given host using SSH."""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if identification_file_content:
                key = paramiko.RSAKey(file_obj=io.StringIO(identification_file_content))
                client.connect(hostname=ip, port=port, username=username, pkey=key, timeout=10)
            else:
                client.connect(hostname=ip, port=port, username=username, password=password, timeout=10)

            for command in commands:
                stdin, stdout, stderr = client.exec_command(command, timeout=30)
                output = stdout.read().decode('utf-8')
                error = stderr.read().decode('utf-8')
                if error:
                    print(f"Warning while executing {command}: {error}")

            client.close()
        except Exception as e:
            raise Exception(f"Failed to execute commands: {str(e)}")

async def setup(bot):
    await bot.add_cog(AddHostCommand(bot))
