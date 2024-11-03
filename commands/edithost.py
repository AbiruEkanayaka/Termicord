import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import tempfile
import os
from typing import List

class EditHostCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.describe(
        hostname="The current hostname of the host to edit",
        hostname_edit="New hostname to set (optional)",
        ip="New IP address (optional)",
        username="New username to set (optional)",
        password="New password (optional)",
        identification_file="New identification file to upload (optional)",
        port="New port number (optional)"
    )
    @app_commands.command(name="edit-host", description="Edit an existing host")
    async def edit_host(
        self,
        interaction: discord.Interaction,
        hostname: str,
        hostname_edit: Optional[str] = None,
        ip: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        identification_file: Optional[discord.Attachment] = None,
        port: Optional[int] = None
    ):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        db = self.bot.db

        async with db.acquire() as conn:
            host = await conn.fetchrow(
                """SELECT * FROM hosts WHERE user_id = $1 AND hostname = $2""",
                user_id, hostname
            )
            if not host:
                await interaction.followup.send(f"No host found with the name '{hostname}'.")
                return

            identification_file_content = None
            if identification_file:
                temp_file_path = os.path.join(tempfile.gettempdir(), identification_file.filename)
                await identification_file.save(temp_file_path)
                with open(temp_file_path, "rb") as f:
                    identification_file_content = f.read().decode('utf-8')
                os.remove(temp_file_path)

            update_fields = []
            update_values = [user_id, hostname] 
            placeholder_index = 3 

            if hostname_edit:
                update_fields.append(f"hostname = ${placeholder_index}")
                update_values.append(hostname_edit)
                placeholder_index += 1
            if ip:
                update_fields.append(f"ip = ${placeholder_index}")
                update_values.append(ip)
                placeholder_index += 1
            if username:
                update_fields.append(f"username = ${placeholder_index}")
                update_values.append(username)
                placeholder_index += 1
            if password:
                update_fields.append(f"password = ${placeholder_index}")
                update_values.append(password)
                placeholder_index += 1
            if identification_file_content:
                update_fields.append(f"identification_file = ${placeholder_index}")
                update_values.append(identification_file_content)
                placeholder_index += 1
            if port:
                update_fields.append(f"port = ${placeholder_index}")
                update_values.append(port)
                placeholder_index += 1

            if not update_fields:
                await interaction.followup.send("No updates provided.")
                return

            try:
                await conn.execute(
                    f"""UPDATE hosts
                        SET {', '.join(update_fields)}
                        WHERE user_id = $1 AND hostname = $2""",
                    *update_values
                )
            except Exception as e:
                print(f"An error occurred: {e}")
                await interaction.followup.send(f"An error occurred while editing host '{hostname}'. Please try again later.")
                return

        await interaction.followup.send(f"Host '{hostname}' updated successfully.")
    
    @edit_host.autocomplete("hostname")
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
    await bot.add_cog(EditHostCommand(bot))
