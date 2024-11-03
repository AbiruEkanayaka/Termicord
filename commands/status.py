import discord
from discord.ext import commands
import paramiko
from discord import app_commands
import os
import re
from typing import List

class StatusCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def strip_ansi_codes(self, text: str) -> str:
        """Remove ANSI escape sequences from the text."""
        ansi_escape = re.compile(r'\x1B\[[0-?9;]*[mK]')
        return ansi_escape.sub('', text).replace('\x1b[?25h', '').replace('\x1b[?25l', '')

    def parse_cpu_info(self, cpu_info: str) -> str:
        """Parse CPU model name from /proc/cpuinfo."""
        for line in cpu_info.split('\n'):
            if 'model name' in line:
                return line.split(':')[1].strip()
        return "Unknown CPU"

    def format_memory(self, total_kb: int, used_kb: int) -> str:
        """Format memory values to MB with proper formatting."""
        total_mb = total_kb / 1024
        used_mb = used_kb / 1024
        return f"{used_mb:.0f}MB / {total_mb:.0f}MB"

    def format_uptime(self, uptime_seconds: float) -> str:
        """Format uptime into a human-readable string."""
        if uptime_seconds < 3600:
            return f"{(uptime_seconds / 60):.1f} minutes"
        else:
            return f"{(uptime_seconds / 3600):.1f} hours"

    def safe_float_convert(self, value: str, default: float = 0.0) -> float:
        """Safely convert string to float with default value."""
        try:
            return float(value.strip())
        except (ValueError, AttributeError):
            return default

    def get_network_usage(self, client) -> str:
        command = "sar -n DEV 1 1 | grep -E 'ens|eth|eno' | head -n 1 | awk '{print $5 + $6}'"

        try:
            stdin, stdout, stderr = client.exec_command(command)
            result = self.strip_ansi_codes(stdout.read().decode()).strip()
            error = stderr.read().decode().strip()

            if result and self.safe_float_convert(result) > 0:
                cx = self.safe_float_convert(result)
                mbps = cx / 1024
                return f"{mbps:.1f} Mbps"
            
        except Exception as e:
            return "N/A"

        return "N/A"

    def get_cpu_usage(self, client) -> str:
        """Get CPU usage with fallback commands."""
        commands = [
            "vmstat 1 2 | tail -1 | awk '{print 100-$15}'"
        ]

        for command in commands:
            try:
                stdin, stdout, stderr = client.exec_command(command)
                result = self.strip_ansi_codes(stdout.read().decode()).strip()
                error = stderr.read().decode().strip()

                if result and self.safe_float_convert(result) > 0:
                    return f"{self.safe_float_convert(result):.1f}%"
            except Exception as e:
                continue
        
        return "N/A"

    @app_commands.describe(hostname="The hostname of the host to check status")
    @app_commands.command(name="status", description="Get system status information from a selected host")
    async def status(
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
                await interaction.followup.send(f"An error occurred while getting status from host '{hostname}'. Please try again later.")
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

                # Get CPU info
                stdin, stdout, stderr = client.exec_command('cat /proc/cpuinfo')
                cpu_info = self.strip_ansi_codes(stdout.read().decode())
                cpu_name = self.parse_cpu_info(cpu_info)

                # Get CPU usage with fallback
                cpu_usage = self.get_cpu_usage(client)

                # Get memory info
                stdin, stdout, stderr = client.exec_command("free | grep Mem:")
                mem_output = self.strip_ansi_codes(stdout.read().decode())
                try:
                    mem_values = mem_output.split()
                    total_kb = int(mem_values[1])
                    used_kb = int(mem_values[2])
                    memory_usage = self.format_memory(total_kb, used_kb)
                except (IndexError, ValueError):
                    memory_usage = "N/A"

                # Get uptime
                stdin, stdout, stderr = client.exec_command('cat /proc/uptime')
                uptime_output = self.strip_ansi_codes(stdout.read().decode())
                try:
                    uptime_seconds = float(uptime_output.split()[0])
                    uptime = self.format_uptime(uptime_seconds)
                except (IndexError, ValueError):
                    uptime = "N/A"

                # Get network usage with fallback
                network_usage = self.get_network_usage(client)

                embed = discord.Embed(
                    title=f"📊 System Status for {hostname}",
                    color=discord.Color.blue()
                )

                embed.add_field(
                    name="💻 CPU",
                    value=f"**Model:** {cpu_name}\n**Usage:** {cpu_usage}",
                    inline=False
                )

                embed.add_field(
                    name="🧮 Memory Usage",
                    value=memory_usage,
                    inline=True
                )

                embed.add_field(
                    name="⏰ Uptime",
                    value=uptime,
                    inline=True
                )

                embed.add_field(
                    name="🌐 Network Usage",
                    value=network_usage,
                    inline=True
                )

                await interaction.followup.send(embed=embed)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}")
            finally:
                client.close()
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

    @status.autocomplete("hostname")
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
    await bot.add_cog(StatusCommand(bot))