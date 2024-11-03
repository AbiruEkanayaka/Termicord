import discord
from discord.ext import commands
import paramiko
from discord import app_commands
import os
from typing import List, Optional
import re
from datetime import datetime
import math

class UsersPaginator(discord.ui.View):
    def __init__(self, users: List[dict], users_per_page: int = 3):
        super().__init__(timeout=180)  # 3 minutes timeout
        self.users = users
        self.users_per_page = users_per_page
        self.current_page = 0
        self.total_pages = math.ceil(len(users) / users_per_page)
        
        # Update button states
        self.update_buttons()

    def update_buttons(self):
        self.first_page_button.disabled = self.current_page == 0
        self.prev_page_button.disabled = self.current_page == 0
        self.next_page_button.disabled = self.current_page >= self.total_pages - 1
        self.last_page_button.disabled = self.current_page >= self.total_pages - 1

    def get_page_content(self) -> discord.Embed:
        start_idx = self.current_page * self.users_per_page
        end_idx = min(start_idx + self.users_per_page, len(self.users))
        page_users = self.users[start_idx:end_idx]

        embed = discord.Embed(
            title="👥 Logged-in Users",
            description=f"Showing users {start_idx + 1}-{end_idx} of {len(self.users)}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        # Add server stats at the top
        stats_value = (
            f"📊 **Total Users:** {len(self.users)}\n"
            f"📄 **Page:** {self.current_page + 1}/{self.total_pages}\n"
            f"⏰ **Last Updated:** {discord.utils.format_dt(datetime.now(), 'R')}"
        )
        embed.add_field(name="Server Statistics", value=stats_value, inline=False)

        # Add a thin line separator using embed description
        embed.description += "\n\n─────────────────────────\n\n"

        for user in page_users:
            # Create a more visually appealing user entry
            session_time = user.get('login_time', 'Unknown')
            idle_time = user.get('idle', 'Active')
            activity = user.get('what', 'No activity')
            ip_display = user.get('ip', 'local').replace('(', '').replace(')', '')

            status_emoji = "🟢" if idle_time == 'Active' else "🔴"
            
            user_header = f"{status_emoji} **{user['username']}** on `{user['terminal']}`"
            
            user_details = (
                f"┌ 🌐 **Connection:** `{ip_display}`\n"
                f"├ ⏰ **Session:** `{session_time}`\n"
                f"├ ⌛ **Idle:** `{idle_time}`\n"
                f"└ 🔄 **Activity:** `{activity}`"
            )

            embed.add_field(
                name=user_header,
                value=user_details,
                inline=False
            )

        # Add footer with navigation help
        embed.set_footer(text="Use the buttons below to navigate between pages • Updates automatically every 3 minutes")
        return embed

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.blurple, custom_id="first_page")
    async def first_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_content(), view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.blurple, custom_id="prev_page")
    async def prev_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_content(), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.blurple, custom_id="next_page")
    async def next_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_content(), view=self)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.blurple, custom_id="last_page")
    async def last_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = self.total_pages - 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_content(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

class UsersCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def strip_ansi_codes(self, text: str) -> str:
        """Remove ANSI escape sequences from the text."""
        ansi_escape = re.compile(r'\x1B\[[0-?9;]*[mK]')
        return ansi_escape.sub('', text).replace('\x1b[?25h', '').replace('\x1b[?25l', '')

    def parse_users(self, who_output: str, w_output: str) -> List[dict]:
        """Parse and combine user information from who and w commands."""
        users = []
        
        # Parse basic user info from who command
        who_lines = who_output.strip().split('\n')
        for line in who_lines:
            if not line.strip():
                continue
                
            parts = line.split()
            if len(parts) >= 5:
                user = {
                    'username': parts[0],
                    'terminal': parts[1],
                    'ip': parts[2] if '(' in parts[2] else 'local',
                    'login_time': ' '.join(parts[3:5]),
                    'idle': 'Active',
                    'what': 'No activity'
                }
                users.append(user)

        # Enhance with w command information
        w_lines = w_output.strip().split('\n')[2:]
        for line in w_lines:
            if not line.strip():
                continue
                
            parts = line.split()
            if len(parts) >= 4:
                username = parts[0]
                # Find matching user from who output
                for user in users:
                    if user['username'] == username and parts[1] == user['terminal']:
                        user['idle'] = parts[3] if parts[3] != '.' else 'Active'
                        user['what'] = ' '.join(parts[7:]) if len(parts) > 7 else 'No activity'

        return users

    @app_commands.describe(hostname="The hostname of the host to check logged-in users")
    @app_commands.command(name="users", description="Get information about logged-in users on a selected host")
    async def users(
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
                print(f"An error occurred: {e}")
                await interaction.followup.send(f"An error occurred while getting users from host '{hostname}'. Please try again later.")
                return

            if not host_data:
                await interaction.followup.send("Host not found. Check your configured hosts.")
                return

            ip, username, password, identification_file, port = host_data

            # Temporary file creation for SSH key
            temp_file_path = f"temp.pem"
            if identification_file:
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
                        password=password,
                        port=port or 22,
                        timeout=10
                    )

                stdin, stdout, stderr = client.exec_command('who')
                who_output = self.strip_ansi_codes(stdout.read().decode())

                stdin, stdout, stderr = client.exec_command('w')
                w_output = self.strip_ansi_codes(stdout.read().decode())

                users = self.parse_users(who_output, w_output)

                if not users:
                    await interaction.followup.send(
                        embed=discord.Embed(
                            title="👥 Logged-in Users",
                            description="No users currently logged in.",
                            color=discord.Color.orange()
                        )
                    )
                    return

                view = UsersPaginator(users)
                message = await interaction.followup.send(embed=view.get_page_content(), view=view)
                view.message = message

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}")
            finally:
                client.close()
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

    @users.autocomplete("hostname")
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
    await bot.add_cog(UsersCommand(bot))