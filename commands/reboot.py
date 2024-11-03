import discord 
from discord.ext import commands
import paramiko
from discord import app_commands
import os
import asyncio
from typing import List

class RebootCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.describe(hostname="The hostname of the host to execute the command on")
    @app_commands.command(name="reboot", description="Reboot a selected host")
    async def reboot(
        self,
        interaction: discord.Interaction,
        hostname: str
    ):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        db = self.bot.db

        async with db.acquire() as conn:
            try:
                host_data = await conn.fetchrow(
                    "SELECT ip, username, password, identification_file, port FROM hosts WHERE user_id = $1 AND hostname = $2",
                    user_id, hostname
                )
            except Exception as e:
                print(f"Database error: {e}")
                await self.send_embed(interaction, "Error", "An error occurred while rebooting the host. Please try again later.", discord.Color.red())
                return

            if not host_data:
                await self.send_embed(interaction, "Host Not Found", "Host not found. Check your configured hosts.", discord.Color.orange())
                return

            ip, username, password, identification_file, port = host_data

            # Temporary file creation
            temp_file_path = "temp.pem"
            with open(temp_file_path, "w") as temp_file:
                temp_file.write(identification_file)

            try:
                # SSH connection setup
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                if identification_file:
                    client.connect(
                        hostname=ip,
                        username=username,
                        port=port or 22,
                        key_filename=temp_file_path,
                        timeout=10
                    )
                else:
                    client.connect(
                        hostname=ip,
                        username=username,
                        port=port or 22,
                        password=password,
                        timeout=10
                    )

                # Execute command
                stdin, stdout, stderr = client.exec_command("sudo reboot")
                error = stderr.read().decode("utf-8")

                if error:
                    await self.send_embed(interaction, "Reboot Error", f"An error occurred while rebooting host '{hostname}': {error}", discord.Color.red())
                else:
                    await self.send_embed(interaction, "Rebooting", f"🔄 Rebooting host '{hostname}'... Please wait for reconnection.", discord.Color.blue())

                success = await self.try_reconnect(interaction, ip, username, password, identification_file, port)

                if success:
                    await self.send_embed(interaction, "Reboot Successful", f"✅ Host '{hostname}' has successfully restarted and is back online!", discord.Color.green())
                else:
                    await self.send_embed(interaction, "Reconnect Failed", f"❌ Failed to reconnect to '{hostname}' after 60 seconds.", discord.Color.red())

            except Exception as e:
                print(f"SSH error: {e}")
                await self.send_embed(interaction, "Error", f"An error occurred while rebooting host '{hostname}'. Please try again later.", discord.Color.red())
            finally:
                client.close()
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

    async def try_reconnect(self, interaction, ip, username, password, identification_file, port):
        """Attempt to reconnect to the VM for 60 seconds."""
        temp_file_path = "temp.pem"
        with open(temp_file_path, "w") as temp_file:
            temp_file.write(identification_file)
        for _ in range(6):
            await asyncio.sleep(10)
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                if identification_file:
                    client.connect(
                        hostname=ip,
                        username=username,
                        port=port or 22,
                        key_filename=temp_file_path,
                        timeout=10
                    )
                else:
                    client.connect(
                        hostname=ip,
                        username=username,
                        port=port or 22,
                        password=password,
                        timeout=10
                    )
                client.close()
                return True 
            except Exception:
                continue 

        return False

    async def send_embed(self, interaction: discord.Interaction, title: str, description: str, color: discord.Color):
        """Sends an embed message to the interaction channel."""
        embed = discord.Embed(title=title, description=description, color=color)
        await interaction.followup.send(embed=embed)

    @reboot.autocomplete("hostname")
    async def reboot_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        user_id = str(interaction.user.id)
        db = self.bot.db
        async with db.acquire() as conn:
            try:
                hostnames = await conn.fetch(
                    "SELECT hostname FROM hosts WHERE user_id = $1",
                    user_id
                )
            except Exception as e:
                print(f"Database error: {e}")
                return []

        return [app_commands.Choice(name=hostname["hostname"], value=hostname["hostname"]) for hostname in hostnames]

async def setup(bot):
    await bot.add_cog(RebootCommand(bot))
