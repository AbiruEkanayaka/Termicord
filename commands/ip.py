import discord
from discord.ext import commands
import paramiko
from discord import app_commands
import os
from typing import List
import re

class IPCommand(commands.GroupCog, name="ip"):
    def __init__(self, bot):
        self.bot = bot

    def strip_ansi_codes(self, text: str) -> str:
        """Remove ANSI escape sequences from the text."""
        ansi_escape = re.compile(r'\x1B\[[0-?9;]*[mK]')
        return ansi_escape.sub('', text).replace('\x1b[?25h', '').replace('\x1b[?25l', '')

    def get_private_ips(self, client) -> dict:
        """Get private IPs for different interfaces."""
        commands = [
            "ip addr show | grep -E 'inet ' | grep -v '127.0.0.1' | awk '{print $2,$NF}'",
            "ifconfig | grep -E 'inet ' | grep -v '127.0.0.1' | awk '{print $2,$NF}'"
        ]

        for command in commands:
            try:
                stdin, stdout, stderr = client.exec_command(command)
                output = self.strip_ansi_codes(stdout.read().decode()).strip()
                
                if output:
                    interfaces = {}
                    for line in output.split('\n'):
                        if line.strip():
                            ip, interface = line.split()
                            interfaces[interface] = ip.split('/')[0]  # Remove CIDR notation
                    return interfaces
            except:
                continue
        
        return {}

    def get_public_ip(self, client) -> str:
        """Get public IP using various services."""
        commands = [
            "curl -s ifconfig.me",
            "curl -s icanhazip.com",
            "curl -s ipecho.net/plain",
            "wget -qO- ipinfo.io/ip"
        ]

        for command in commands:
            try:
                stdin, stdout, stderr = client.exec_command(command)
                ip = self.strip_ansi_codes(stdout.read().decode()).strip()
                if ip and len(ip.split('.')) == 4:  # Basic IP validation
                    return ip
            except:
                continue
        
        return "Unable to determine public IP"

    @app_commands.describe(hostname="The hostname of the host to check private IPs")
    @app_commands.command(name="private", description="Get private IP addresses for a host")
    async def private(
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
                await interaction.followup.send(f"An error occurred while getting IPs from host '{hostname}'. Please try again later.")
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
                        key_filename=temp_file_path
                    )
                else:
                    client.connect(
                        hostname=ip,
                        username=username,
                        password=password,
                        port=port or 22
                    )

                private_ips = self.get_private_ips(client)

                embed = discord.Embed(
                    title=f"🔒 Private IP Addresses for {hostname}",
                    color=discord.Color.blue(),
                    description="List of all private IP addresses by network interface"
                )

                if private_ips:
                    for interface, ip in private_ips.items():
                        embed.add_field(
                            name=f"🌐 Interface: {interface}",
                            value=f"```{ip}```",
                            inline=False
                        )
                else:
                    embed.description = "❌ No private IP addresses found"

                await interaction.followup.send(embed=embed)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}")
            finally:
                client.close()
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

    @app_commands.describe(hostname="The hostname of the host to check public IP")
    @app_commands.command(name="public", description="Get public IP address for a host")
    async def public(
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
                await interaction.followup.send(f"An error occurred while getting IP from host '{hostname}'. Please try again later.")
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

                public_ip = self.get_public_ip(client)

                embed = discord.Embed(
                    title=f"🌍 Public IP Address for {hostname}",
                    color=discord.Color.green()
                )

                if public_ip != "Unable to determine public IP":
                    embed.add_field(
                        name="🔍 Public IP",
                        value=f"```{public_ip}```",
                        inline=False
                    )
                    
                    embed.add_field(
                        name="ℹ️ IP Info",
                        value=f"[View Details](https://ipinfo.io/{public_ip})",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="❌ Error",
                        value="Unable to determine public IP address",
                        inline=False
                    )

                await interaction.followup.send(embed=embed)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}")
            finally:
                client.close()
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

    @private.autocomplete("hostname")
    @public.autocomplete("hostname")
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
    await bot.add_cog(IPCommand(bot))