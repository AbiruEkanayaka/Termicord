import discord
from discord.ext import commands
import paramiko
from discord import app_commands
import os
import re
from typing import List, Dict
from collections import defaultdict

class PortsCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def strip_ansi_codes(self, text: str) -> str:
        """Remove ANSI escape sequences from the text."""
        ansi_escape = re.compile(r'\x1B\[[0-?]*[mK]')
        return ansi_escape.sub('', text).replace('\x1b[?25h', '').replace('\x1b[?25l', '')

    def get_ports_command(self) -> str:
        """Returns the bash command to get open ports information using ss."""
        return '''
            ss -tulnp | grep LISTEN; ss -tulnp | grep UNCONN
        '''

    def parse_port_info(self, output: str) -> Dict:
        """Parse the command output and organize port information."""
        info = {}
        processes = defaultdict(str)

        for line in output.strip().split('\n'):
            parts = line.split()
            if len(parts) < 6:
                continue

            protocol = parts[0]
            local_address = parts[4]
            process_info = parts[-1]

            port = local_address.split(':')[-1] 
            if protocol == 'tcp':
                info.setdefault('TCP_PORTS', []).append(port)
            elif protocol == 'udp':
                info.setdefault('UDP_PORTS', []).append(port)

            # Extract process information
            if process_info != '-':
                process = process_info.split(',')[1] if ',' in process_info else 'N/A'
                processes[port] = process.split('/')[0] 

        return {
            'tcp_ports': info.get('TCP_PORTS', []),
            'udp_ports': info.get('UDP_PORTS', []),
            'processes': processes
        }

    def safe_port_sort(self, ports: List[str]) -> List[str]:
        """Safely sort ports, handling non-numeric and empty values."""
        def port_key(port):
            try:
                return int(port.strip())
            except (ValueError, AttributeError):
                return 0 

        return sorted([p for p in ports if p.strip()], key=port_key)

    def get_common_port_service(self, port: str) -> str:
        """Returns common service names for well-known ports."""
        common_ports = {
            '21': 'FTP',
            '22': 'SSH',
            '23': 'Telnet',
            '25': 'SMTP',
            '53': 'DNS',
            '80': 'HTTP',
            '443': 'HTTPS',
            '3306': 'MySQL',
            '5432': 'PostgreSQL',
            '6379': 'Redis',
            '27017': 'MongoDB',
            '8080': 'HTTP-ALT',
            '8443': 'HTTPS-ALT',
            '1194': 'OpenVPN',
            '3389': 'RDP',
            '5900': 'VNC',
            '8888': 'HTTP Proxy'
        }
        return common_ports.get(port.strip(), 'Unknown')

    @app_commands.describe(hostname="The hostname of the host to check open ports")
    @app_commands.command(name="ports", description="List all open ports on a selected host")
    async def ports(
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
                await interaction.followup.send(f"An error occurred while checking ports on host '{hostname}'. Please try again later.")
                return

            if not host_data:
                await interaction.followup.send("Host not found. Check your configured hosts.")
                return

            ip, username, password, identification_file, port = host_data

            # Temporary file creation for SSH key if needed
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

                # Execute command to get ports info
                stdin, stdout, stderr = client.exec_command(self.get_ports_command())
                output = self.strip_ansi_codes(stdout.read().decode())

                port_info = self.parse_port_info(output)

                embed = discord.Embed(
                    title=f"🔍 Open Ports on {hostname}",
                    color=discord.Color.green()
                )

                tcp_description = ""
                for port in self.safe_port_sort(port_info['tcp_ports']):
                    if port.strip():  # Only process non-empty ports
                        service = self.get_common_port_service(port)
                        process = port_info['processes'].get(port, 'N/A')
                        tcp_description += f"🔐 Port {port} ({service})\n└─ Process: {process}\n"

                if tcp_description:
                    embed.add_field(
                        name="📡 TCP Ports",
                        value=f"```{tcp_description}```",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="📡 TCP Ports",
                        value="```No TCP ports found```",
                        inline=False
                    )

                udp_description = ""
                for port in self.safe_port_sort(port_info['udp_ports']):
                    if port.strip():  # Only process non-empty ports
                        service = self.get_common_port_service(port)
                        process = port_info['processes'].get(port, 'N/A')
                        udp_description += f"🔓 Port {port} ({service})\n└─ Process: {process}\n"

                if udp_description:
                    embed.add_field(
                        name="📡 UDP Ports",
                        value=f"```{udp_description}```",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="📡 UDP Ports",
                        value="```No UDP ports found```",
                        inline=False
                    )

                embed.set_footer(text="🔒 Shows listening ports and associated processes")
                await interaction.followup.send(embed=embed)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}")
            finally:
                client.close()
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

    @ports.autocomplete("hostname")
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
    await bot.add_cog(PortsCommand(bot))
