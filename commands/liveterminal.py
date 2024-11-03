import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Dict
import paramiko
import asyncio
import re
import os

class LiveTerminalCommand(commands.GroupCog, name="live-terminal"):
    def __init__(self, bot):
        self.bot = bot
        self.active_terminals: Dict[int, Dict] = {}
        self.bot.loop.create_task(self.initialize_terminals())
        
    async def initialize_terminals(self):
        """Initialize all active terminals from the database on startup."""
        await self.bot.wait_until_ready()
        async with self.bot.db.acquire() as conn:
            active_sessions = await conn.fetch(
                """SELECT lt.channel_id, lt.user_id, lt.hostname, 
                          h.ip, h.username, h.password, h.identification_file, h.port
                   FROM live_terminals lt
                   JOIN hosts h ON lt.user_id = h.user_id AND lt.hostname = h.hostname
                   WHERE lt.is_active = true"""
            )
            
            for session in active_sessions:
                channel = self.bot.get_channel(int(session['channel_id']))
                if channel:
                    await self.restore_terminal_session(session, channel)

    async def restore_terminal_session(self, session, channel):
        """Restore an individual terminal session from the database."""
        try:
            client = self.create_ssh_client(session)
            shell = client.invoke_shell()
            shell.send('export TERM=xterm\n')
            shell.send('set +o vi\n')
            shell.send('stty -echo\n')
            
            self.active_terminals[int(session['channel_id'])] = {
                'client': client,
                'shell': shell,
                'user_id': session['user_id'],
                'output_buffer': ''
            }
            
            # Start output monitoring task
            self.bot.loop.create_task(self.monitor_shell_output(channel, shell))
            await channel.send("Terminal session restored after bot restart.")
            
        except Exception as e:
            await channel.send(f"Failed to restore terminal session: {e}")
            await self.cleanup_terminal(int(session['channel_id']))

    def create_ssh_client(self, session) -> paramiko.SSHClient:
        """Create and connect an SSH client."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if session['identification_file']:
            temp_file_path = f"temp_{session['channel_id']}.pem"
            with open(temp_file_path, "w") as temp_file:
                temp_file.write(session['identification_file'])
            client.connect(
                hostname=session['ip'],
                username=session['username'],
                port=session['port'] or 22,
                key_filename=temp_file_path,
                timeout=10
            )
        else:
            client.connect(
                hostname=session['ip'],
                username=session['username'],
                password=session['password'],
                port=session['port'] or 22,
                timeout=10
            )
        os.remove(temp_file_path)
        return client

    def clean_terminal_output(self, text: str) -> str:
        """Clean terminal output of control sequences and format it properly."""
        patterns = [
            r'\x1B\[[0-?]*[ -/]*[@-~]',
            r'\x1B\][0-9;]*\x07',
            r'\x1B[PX^_][0-9;]*[\\]',
            r'\x1B[=>]',
            r'\x1B[0-9;]*[A-Za-z]',
            r'\x1B\[[0-9;]*[mK]',
            r'\x1B\[[\x30-\x3F]*[\x20-\x2F]*[\x40-\x7E]',
            r'\[[\d;]+[A-Za-z]',
            r'\[\?[0-9;]*[a-zA-Z]',
            r'\[[0-9]+[A-Z]',
            r'\x1B\[[\d;]*[A-Za-z]',
        ]

        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned)

        cleaned = cleaned.replace('\x1b[?2004h', '')
        cleaned = cleaned.replace('\x1b[?2004l', '')
        cleaned = cleaned.replace('\x1b[?7h', '')
        cleaned = cleaned.replace('\x1b[?7l', '')

        cleaned = re.sub(r'\[\d+;\d+[A-Z]', '', cleaned)
        cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)
        cleaned = cleaned.strip()
        
        return cleaned

    @app_commands.describe(
        hostname="The hostname of the host to connect to",
        channel="The text channel to use for the live terminal"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.command(name="start", description="Start a live terminal session in a specified channel")
    async def live_terminal(
        self,
        interaction: discord.Interaction,
        hostname: str,
        channel: discord.TextChannel
    ):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        db = self.bot.db

        if channel.id in self.active_terminals:
            await interaction.followup.send("There's already an active terminal session in this channel.")
            return

        async with db.acquire() as conn:
            try:
                await conn.execute(
                    """INSERT INTO live_terminals (user_id, hostname, channel_id, is_active)
                    VALUES ($1, $2, $3, true)
                    ON CONFLICT (channel_id) DO UPDATE
                    SET user_id = $1, hostname = $2, is_active = true""",
                    user_id, hostname, str(channel.id)
                )

                host_data = await conn.fetchrow(
                    "SELECT ip, username, password, identification_file, port FROM hosts WHERE user_id = $1 AND hostname = $2",
                    user_id, hostname
                )

                if not host_data:
                    await interaction.followup.send("Host not found. Please check your configured hosts.")
                    return

                ip, username, password, identification_file, port = host_data

                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                if identification_file:
                    temp_file_path = f"temp_{channel.id}.pem"
                    with open(temp_file_path, "w") as temp_file:
                        temp_file.write(identification_file)
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

                shell = client.invoke_shell()
                shell.send('export TERM=xterm\n')
                shell.send('set +o vi\n')
                shell.send('stty -echo\n')
                
                self.active_terminals[channel.id] = {
                    'client': client,
                    'shell': shell,
                    'user_id': user_id,
                    'output_buffer': ''
                }

                self.bot.loop.create_task(self.monitor_shell_output(channel, shell))
                await interaction.followup.send(f"Live terminal started in {channel.mention}. You can now send commands directly in this channel.")
                os.remove(temp_file_path)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}")
                await self.cleanup_terminal(channel.id)

    @app_commands.command(name="list", description="List all active live terminal sessions.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list_terminals(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        if not self.active_terminals:
            await interaction.followup.send("No active terminal sessions found.")
            return

        embed = discord.Embed(title="Active Terminal Sessions", color=discord.Color.blue())
        
        for channel_id, terminal in self.active_terminals.items():
            channel = self.bot.get_channel(channel_id)
            user_id = terminal['user_id']
            user = await self.bot.fetch_user(user_id) 
            
            host_info = terminal.get('hostname', 'Unknown')

            embed.add_field(
                name=f"Terminal in {channel.mention} 🖥️",
                value=(
                    f"**User:** {user.name}\n"
                    f"**Host:** {host_info}\n"
                    f"**Channel ID:** {channel_id}\n"
                    f"**Status:** Active ✅\n\n"
                ),
                inline=False
            )

        embed.set_footer(text="Use /live-terminal stop to end any active session.")

        await interaction.followup.send(embed=embed)

    async def monitor_shell_output(self, channel: discord.TextChannel, shell):
        """Monitor and send shell output to the Discord channel."""
        try:
            while channel.id in self.active_terminals:
                if shell.recv_ready():
                    terminal_data = self.active_terminals[channel.id]
                    chunk = shell.recv(4096).decode('utf-8', errors='ignore')
                    terminal_data['output_buffer'] += chunk
                    
                    if '\n' in terminal_data['output_buffer'] or len(terminal_data['output_buffer']) > 1500:
                        cleaned_output = self.clean_terminal_output(terminal_data['output_buffer'])
                        if cleaned_output.strip():
                            chunks = [cleaned_output[i:i + 1900] for i in range(0, len(cleaned_output), 1900)]
                            for chunk in chunks:
                                if chunk.strip():
                                    await channel.send(f"```\n{chunk}\n```")
                        terminal_data['output_buffer'] = ''
                
                await asyncio.sleep(0.1)

        except Exception as e:
            await channel.send(f"Error in terminal monitoring: {e}")
            await self.cleanup_terminal(channel.id)

    async def get_terminal_session_data(self, channel_id: int):
        """Fetch session data for reconnection."""
        async with self.bot.db.acquire() as conn:
            return await conn.fetchrow(
                """SELECT lt.hostname, h.ip, h.username, h.password, 
                        h.identification_file, h.port,
                        lt.channel_id, lt.user_id
                FROM live_terminals lt 
                JOIN hosts h ON lt.user_id = h.user_id AND lt.hostname = h.hostname
                WHERE lt.channel_id = $1 AND lt.is_active = true""",
                str(channel_id)
            )

    async def handle_disconnection(self, channel_id: int):
        """Handle disconnections by attempting to reconnect."""
        if channel_id in self.active_terminals:
            terminal_data = self.active_terminals[channel_id]
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send("Connection lost. Attempting to reconnect...")
                
                if terminal_data.get('reconnecting', False):
                    await channel.send("Already attempting to reconnect.")
                    return
                
                terminal_data['reconnecting'] = True
                
                try:
                    for attempt in range(3):
                        try:
                            if 'client' in terminal_data:
                                try:
                                    terminal_data['client'].close()
                                except Exception:
                                    pass  # Ignore errors during client closure
                            
                            session = await self.get_terminal_session_data(channel_id)
                            if not session:
                                await channel.send("Could not find active terminal session data.")
                                break
                                
                            # Create temporary key file if needed
                            temp_file_path = None
                            try:
                                if session['identification_file']:
                                    temp_file_path = f"temp_{channel_id}.pem"
                                    with open(temp_file_path, "w") as temp_file:
                                        temp_file.write(session['identification_file'])
                                
                                # Create new SSH client
                                new_client = paramiko.SSHClient()
                                new_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                                
                                connect_kwargs = {
                                    'hostname': session['ip'],
                                    'username': session['username'],
                                    'port': session['port'] or 22,
                                    'timeout': 10
                                }
                                
                                if session['identification_file']:
                                    connect_kwargs['key_filename'] = temp_file_path
                                else:
                                    connect_kwargs['password'] = session['password']
                                    
                                new_client.connect(**connect_kwargs)
                                new_shell = new_client.invoke_shell()
                                
                                # Initialize terminal settings
                                new_shell.send('export TERM=xterm\n')
                                new_shell.send('set +o vi\n')
                                new_shell.send('stty -echo\n')
                                
                                # Update terminal data
                                terminal_data.update({
                                    'shell': new_shell,
                                    'client': new_client,
                                    'output_buffer': '',
                                    'user_id': session['user_id'],
                                    'hostname': session['hostname']
                                })
                                
                                await channel.send("Reconnected successfully.")
                                self.bot.loop.create_task(self.monitor_shell_output(channel, new_shell))
                                return
                                
                            finally:
                                # Clean up temporary key file
                                if temp_file_path and os.path.exists(temp_file_path):
                                    try:
                                        os.remove(temp_file_path)
                                    except Exception:
                                        pass
                                        
                        except Exception as e:
                            await channel.send(f"Reconnection attempt {attempt + 1} failed: {str(e)}")
                            await asyncio.sleep(2)
                    
                    await channel.send("All reconnection attempts failed. Terminal session has been terminated.")
                    await self.cleanup_terminal(channel_id)
                    
                finally:
                    terminal_data['reconnecting'] = False

    @app_commands.describe(channel="The channel to stop the live terminal session in")
    @app_commands.command(name="stop", description="Stop the live terminal session in a specified channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def stop_terminal(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer()
        
        channel_id = channel.id
        
        if channel_id not in self.active_terminals:
            await interaction.followup.send("No active terminal session found in this channel.")
            return
        
        await self.delete_terminal(channel_id)
        
        await interaction.followup.send("Terminal session has been stopped and cleaned up.")

    async def delete_terminal(self, channel_id: int):
        """Clean up terminal session resources and remove the database entry."""
        if channel_id in self.active_terminals:
            try:
                self.active_terminals[channel_id]['shell'].close()
                self.active_terminals[channel_id]['client'].close()
                
                async with self.bot.db.acquire() as conn:
                    await conn.execute(
                        """DELETE FROM live_terminals 
                           WHERE channel_id = $1""",
                        str(channel_id)
                    )
            except Exception as e:
                print(f"Error during cleanup: {e}")
            finally:
                del self.active_terminals[channel_id]

    async def cleanup_terminal(self, channel_id: int):
        """Clean up terminal session resources and update database."""
        if channel_id in self.active_terminals:
            try:
                terminal_data = self.active_terminals[channel_id]
                try:
                    if 'shell' in terminal_data:
                        terminal_data['shell'].close()
                    if 'client' in terminal_data:
                        terminal_data['client'].close()
                except Exception:
                    pass  # Ignore errors during closure
                    
                async with self.bot.db.acquire() as conn:
                    await conn.execute(
                        """UPDATE live_terminals 
                        SET is_active = false 
                        WHERE channel_id = $1""",
                        str(channel_id)
                    )
            except Exception as e:
                print(f"Error during cleanup: {e}")
            finally:
                if channel_id in self.active_terminals:
                    del self.active_terminals[channel_id]

    @app_commands.describe(
        channel="The text channel to restart the inactive terminal session"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.command(name="restart", description="Restart an inactive terminal session in a specified channel")
    async def restart_terminal(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        
        if channel.id in self.active_terminals:
            await interaction.followup.send("There's already an active terminal session in this channel.")
            return

        async with self.bot.db.acquire() as conn:
            try:
                # Get the most recent inactive terminal session for this channel
                terminal_data = await conn.fetchrow(
                    """SELECT lt.hostname, h.ip, h.username, h.password, 
                              h.identification_file, h.port
                       FROM live_terminals lt
                       JOIN hosts h ON lt.user_id = h.user_id AND lt.hostname = h.hostname
                       WHERE lt.channel_id = $1 AND lt.is_active = false
                       ORDER BY lt.created_at DESC
                       LIMIT 1""",
                    str(channel.id)
                )

                if not terminal_data:
                    await interaction.followup.send("No previous terminal session found for this channel.")
                    return

                # Update the terminal session to active
                await conn.execute(
                    """UPDATE live_terminals 
                       SET is_active = true, user_id = $1
                       WHERE channel_id = $2 AND hostname = $3""",
                    user_id, str(channel.id), terminal_data['hostname']
                )

                # Create new SSH connection
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                if terminal_data['identification_file']:
                    temp_file_path = f"temp_{channel.id}.pem"
                    with open(temp_file_path, "w") as temp_file:
                        temp_file.write(terminal_data['identification_file'])
                    client.connect(
                        hostname=terminal_data['ip'],
                        username=terminal_data['username'],
                        port=terminal_data['port'] or 22,
                        key_filename=temp_file_path,
                        timeout=10
                    )
                    os.remove(temp_file_path)
                else:
                    client.connect(
                        hostname=terminal_data['ip'],
                        username=terminal_data['username'],
                        password=terminal_data['password'],
                        port=terminal_data['port'] or 22,
                        timeout=10
                    )

                shell = client.invoke_shell()
                shell.send('export TERM=xterm\n')
                shell.send('set +o vi\n')
                shell.send('stty -echo\n')
                
                self.active_terminals[channel.id] = {
                    'client': client,
                    'shell': shell,
                    'user_id': user_id,
                    'output_buffer': '',
                    'hostname': terminal_data['hostname']
                }

                self.bot.loop.create_task(self.monitor_shell_output(channel, shell))
                await interaction.followup.send(
                    f"Previous terminal session restarted in {channel.mention} "
                    f"for host '{terminal_data['hostname']}'. You can now send commands directly in this channel."
                )

            except Exception as e:
                await interaction.followup.send(f"An error occurred while restarting the terminal: {e}")
                await self.cleanup_terminal(channel.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle messages in terminal channels."""
        if message.author.bot:
            return

        channel_id = message.channel.id
        if channel_id in self.active_terminals:
            terminal_data = self.active_terminals[channel_id]
            
            if str(message.author.id) != terminal_data['user_id']:
                return

            command = message.content.strip()
            if command:
                await message.channel.send(f"Executing command: `{command}`")
                try:
                    if command.startswith('^'):
                        command = self.handle_control_input(command)
                    terminal_data['shell'].send(command + '\n')
                except Exception as e:
                    if str(e) == "Socket is closed":
                        await message.channel.send(f"Socket closed while executing command use `/live_terminal restart` to restore session.")
                    else:
                        await message.channel.send(f"Error executing command: {e}")
                    await self.cleanup_terminal(channel_id)

    def handle_control_input(self, command: str) -> str:
        """Convert control input notation to actual control characters."""
        control_mappings = {
            '^X': '\x18',
            '^C': '\x03',
            '^V': '\x16',
        }
        return control_mappings.get(command, command)

    @live_terminal.autocomplete("hostname")
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
    await bot.add_cog(LiveTerminalCommand(bot))
