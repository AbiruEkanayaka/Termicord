import discord
from discord.ext import commands
import paramiko
from discord import app_commands
import os
from typing import List, Tuple
import re
from discord.ui import Button, View

class ProcessPaginationView(View):
    def __init__(self, processes: List[Tuple], page_size: int, sort_type: str, hostname: str):
        super().__init__(timeout=180)
        self.processes = processes
        self.page_size = page_size
        self.current_page = 0
        self.sort_type = sort_type
        self.hostname = hostname
        self.total_pages = (len(processes) + page_size - 1) // page_size
        
        self.update_buttons()

    def update_buttons(self):
        self.first_page_button.disabled = self.current_page == 0
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= (len(self.processes) // self.page_size)
        self.last_page_button.disabled = self.current_page >= (len(self.processes) // self.page_size)

    def get_page_content(self) -> discord.Embed:
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.processes))
        page_processes = self.processes[start_idx:end_idx]

        embed = discord.Embed(
            title=f"🔄 Process Monitor: {self.hostname}",
            description=f"```\n📊 Sorted by {self.sort_type}\n📄 Page {self.current_page + 1} of {self.total_pages}```",
            color=discord.Color.blue()
        )

        sort_indicator = "📈" if "Hi - Lo" in self.sort_type else "📉"
        metric_emoji = "⚡" if "CPU" in self.sort_type else "💾" if "Memory" in self.sort_type else "🌐"
        
        formatted_processes = ""
        for i, process_data in enumerate(page_processes, start=start_idx + 1):
            pid, cpu, mem, command, user, network = process_data

            formatted_processes += (
                f"**{i}.** `{command}`\n"
                f"┣ 👤 User: `{pid}`\n"   # PID and user is swapped idk why
                f"┣ 🔍 PID: `{user}`\n"     # PID and user is swapped idk why
                f"┣ ⚡ CPU: `{cpu}`\n"
                f"┣ 💾 MEM: `{mem}`\n"
                "┗━━━━━━━━━━━\n"
            )
            
            #formatted_processes += f"┗ 🌐 NET: `{network}`\n" if network else "┗━━━━━━━━━━━\n" # Figuring stuff out yet
            formatted_processes += "\n"

        embed.add_field(
            name=f"{sort_indicator} {metric_emoji} Process List",
            value=formatted_processes or "No processes found",
            inline=False
        )

        embed.set_footer(text=f"Use the buttons below to navigate • {self.sort_type} • Refreshed every 60s")

        return embed

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.gray, custom_id="first_page")
    async def first_page_button(self, interaction: discord.Interaction, button: Button):
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_content(), view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary, custom_id="prev_page")
    async def prev_button(self, interaction: discord.Interaction, button: Button):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_content(), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary, custom_id="next_page")
    async def next_button(self, interaction: discord.Interaction, button: Button):
        self.current_page = min(len(self.processes) // self.page_size, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_content(), view=self)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.gray, custom_id="last_page")
    async def last_page_button(self, interaction: discord.Interaction, button: Button):
        self.current_page = len(self.processes) // self.page_size
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_content(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

class ProcessesCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def strip_ansi_codes(self, text: str) -> str:
        ansi_escape = re.compile(r'\x1B\[[0-?9;]*[mK]')
        return ansi_escape.sub('', text)

    SORT_OPTIONS = [
        "CPU Hi - Lo",
        "CPU Lo - Hi",
        "Memory Hi - Lo",
        "Memory Lo - Hi",
        #"Network Hi - Lo", # Figuring Stuff out
        #"Network Lo - Hi"
    ]

    def parse_ps_output(self, output: str) -> List[Tuple[str, str, str, str, str]]:
        lines = output.strip().split('\n')[1:]  # Skip header
        processes = []

        for line in lines:
            parts = line.split()
            if len(parts) >= 11:
                pid = parts[0]
                cpu = float(parts[2])
                mem = float(parts[3])
                command = ' '.join(parts[10:])[:40] 
                user = parts[1] 
                processes.append((pid, f"{cpu:.1f}%", f"{mem:.1f}%", command, user))

        return processes
    
    # Not used yet
    def get_network_usage_by_pid(self, client, pid: str) -> str:
        print(f"Getting network usage for PID {pid}")
        cmd = f"""sudo ss -tunp | grep {pid} | awk '$0="Received: " $2 " bytes, Sent: " $2 " bytes"'"""
        stdin, stdout, stderr = client.exec_command(cmd)
        result = stdout.read().decode().strip()
        try:
            bytes_total = int(result)
            mb_total = bytes_total / (1024 * 1024)
            return f"{mb_total:.1f}MB"
        except (ValueError, IndexError):
            return "N/A"

    @app_commands.command(name="processes", description="Show processes sorted by CPU, Memory, or Network usage")
    @app_commands.describe(
        hostname="The hostname of the host to check processes",
        sort="Sort processes by CPU, Memory, or Network (Hi - Lo or Lo - Hi)"
    )
    @app_commands.choices(sort=[
        app_commands.Choice(name=option, value=option)
        for option in SORT_OPTIONS
    ])
    async def processes(
        self,
        interaction: discord.Interaction,
        hostname: str,
        sort: str = "Memory Hi - Lo"
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
                await interaction.followup.send(f"An error occurred while getting processes from host '{hostname}'. Please try again later.")
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

                # Not yet fully Implemented 
                if "Network" in sort:
                    cmd = "ps aux"  # Get all processes
                    stdin, stdout, stderr = client.exec_command(cmd)
                    output = self.strip_ansi_codes(stdout.read().decode())
                    processes = self.parse_ps_output(output)
                    
                    # Get network usage for each process and include it in processes
                    processes_with_network = []
                    for pid, cpu, mem, command, user in processes[:30]:
                        network = self.get_network_usage_by_pid(client, user)  # Get the network usage
                        processes_with_network.append((pid, cpu, mem, command, user, network if network else "N/A"))
                    
                    # Sort by network usage
                    processes_with_network.sort(
                        key=lambda x: float(x[5].rstrip('MB')) if x[5] != 'N/A' else -1,
                        reverse="Hi - Lo" in sort
                    )
                    
                    processes = processes_with_network
                else:
                    cmd = "ps aux --sort=-%cpu" if "CPU" in sort else "ps aux --sort=-%mem"
                    stdin, stdout, stderr = client.exec_command(cmd)
                    output = self.strip_ansi_codes(stdout.read().decode())
                    processes = self.parse_ps_output(output)[:30]  # Get top 30 for pagination

                    # Add a default "N/A" for network usage when not sorting by it
                    for i in range(len(processes)):
                        processes[i] += ("N/A",)  # Append N/A for network

                view = ProcessPaginationView(processes, page_size=5, sort_type=sort, hostname=hostname)
                embed = view.get_page_content()
                
                message = await interaction.followup.send(embed=embed, view=view)
                view.message = message

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}")
            finally:
                client.close()
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

    @processes.autocomplete("hostname")
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
    await bot.add_cog(ProcessesCommand(bot))
