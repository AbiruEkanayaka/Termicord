import discord
from discord.ext import commands
from discord import app_commands
from collections import deque
import paramiko
import os
import re
import asyncio
from typing import List, Optional
import io

class CommandInputModal(discord.ui.Modal):
    def __init__(self, channel) -> None:
        super().__init__(title="Command Input")
        self.channel = channel

        self.input_text = discord.ui.TextInput(
            label="Enter your input",
            placeholder="Type your input here...",
            required=True,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.input_text)

    async def on_submit(self, interaction: discord.Interaction):
        input_value = self.input_text.value
        if input_value:
            self.channel.send(f"{input_value}\n")
            await interaction.response.send_message("Input sent successfully.", ephemeral=True)
        else:
            await interaction.response.send_message("No input provided. Please try again.", ephemeral=True)

class CommandControls(discord.ui.View):
    def __init__(self, channel, complete_output):
        super().__init__(timeout=None)
        self.channel = channel
        self.is_running = True
        self.complete_output = complete_output
        self.last_activity = asyncio.get_event_loop().time()

    @discord.ui.button(label="Ctrl + C", style=discord.ButtonStyle.danger)
    async def stop_execution(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_running:
            self.channel.send("\x03")  # Send Ctrl+C signal
            self.is_running = False
            await self.cleanup(interaction)
        else:
            await interaction.response.send_message("No execution to stop.", ephemeral=True)

    @discord.ui.button(label="Send Input", style=discord.ButtonStyle.primary)
    async def send_input(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_running:
            self.last_activity = asyncio.get_event_loop().time()  # Update activity timestamp
            modal = CommandInputModal(self.channel)
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message("Command execution has ended.", ephemeral=True)

    @discord.ui.button(label="Finish", style=discord.ButtonStyle.secondary)
    async def finish_execution(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_running:
            self.is_running = False
            await self.cleanup(interaction)
        else:
            await interaction.response.send_message("Command execution has already ended.", ephemeral=True)

    async def cleanup(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True
        
        await interaction.message.edit(view=self)
        
        output_file = discord.File(
            io.StringIO(''.join(self.complete_output)),
            filename="command_output.txt"
        )
        
        await interaction.response.send_message(
            "Execution finished. Full output attached.",
            file=output_file
        )

    def update_activity(self):
        """Update the last activity timestamp"""
        self.last_activity = asyncio.get_event_loop().time()

class ExecuteCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_commands = {}

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

    async def update_output_embed(self, 
                                message: discord.Message, 
                                command: str, 
                                hostname: str, 
                                output_lines: deque,
                                view: Optional[CommandControls] = None,
                                is_final: bool = False) -> None:
        status = "Completed" if is_final else "Executing"
        command_embed = discord.Embed(
            title=f"{status} Command on Host '{hostname}'",
            color=discord.Color.green() if is_final else discord.Color.blue(),
            description=f"**Command:**\n```{command}```\n**Output:**\n```{''.join(output_lines)}```"
        )
        
        if is_final:
            command_embed.set_footer(text="Command execution finished. Full output available in attached file.")
        
        try:
            await message.edit(embed=command_embed, view=view)
        except discord.errors.HTTPException:
            while len(''.join(output_lines)) > 3800:
                output_lines.popleft()
            command_embed.description = f"**Command:**\n```{command}```\n**Output (truncated):**\n```{''.join(output_lines)}```"
            await message.edit(embed=command_embed, view=view)

    async def check_timeout(self, view: CommandControls, message: discord.Message):
        """Check for command timeout"""
        while view.is_running:
            await asyncio.sleep(5) 
            current_time = asyncio.get_event_loop().time()
            if not self.continuous and (current_time - view.last_activity) >= 120: 
                view.is_running = False
                for child in view.children:
                    child.disabled = True
                
                output_file = discord.File(
                    io.StringIO(''.join(view.complete_output)),
                    filename="command_output.txt"
                )
                
                timeout_embed = discord.Embed(
                    title="Command Timed Out",
                    color=discord.Color.orange(),
                    description="Command terminated due to lack of activity for 120 seconds. Full output attached. Use /execute <command> <hostname> <continuous: True> to stop timeouts!"
                )
                await message.edit(embed=timeout_embed, view=view)
                await message.reply(content="Command terminated due to lack of activity for 120 seconds. Full output attached. Use /execute <command> <hostname> <continuous: True> to stop timeouts!", file=output_file)
                break

    async def read_output(self, channel, output_lines: deque, complete_output: list, message: discord.Message, command: str, hostname: str, view: CommandControls):
        """Continuously read output from the SSH channel"""
        last_update = 0
        update_interval = 1
        consecutive_prompts = 0

        asyncio.create_task(self.check_timeout(view, message))

        while True:
            if not view.is_running:
                break

            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                view.is_running = False
                break

            current_time = asyncio.get_event_loop().time()
            output = ""
            
            if channel.recv_ready():
                output += channel.recv(4096).decode('utf-8', errors='ignore')
                view.update_activity() 
            if channel.recv_stderr_ready():
                output += channel.recv_stderr(4096).decode('utf-8', errors='ignore')
                view.update_activity()

            if output:
                cleaned_output = self.clean_terminal_output(output)
                lines = cleaned_output.splitlines()
    
                for i, line in enumerate(lines):
                    if "Last login:" in line:
                        cleaned_output = "\n".join(lines[i + 1:])

                new_lines = cleaned_output.splitlines()
                
                for line in new_lines:
                    if line.strip():
                        output_lines.append(line + '\n')
                        complete_output.append(line + '\n')
                        if len(output_lines) > 50:
                            output_lines.popleft()
                
                if current_time - last_update >= update_interval:
                    await self.update_output_embed(message, command, hostname, output_lines, view)
                    last_update = current_time

            await asyncio.sleep(0.1)

        await self.update_output_embed(message, command, hostname, output_lines, view, is_final=True)

    @app_commands.describe(
            command="The command to execute",
            hostname="The hostname of the host to execute the command on",
            continuous="Whether to run the command in continuous mode won't get automatically stopped after the command is executed"
    )
    @app_commands.command(name="execute", description="Execute a bash command on a selected host")
    async def execute(
        self,
        interaction: discord.Interaction,
        command: str,
        hostname: str,
        continuous: Optional[bool] = False
    ):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        db = self.bot.db
        self.continuous = continuous

        async with db.acquire() as conn:
            try:
                host_data = await conn.fetchrow(
                    "SELECT ip, username, password, identification_file, port FROM hosts WHERE user_id = $1 AND hostname = $2",
                    user_id, hostname
                )
            except Exception as e:
                print(f"An error occurred: {e}")
                await interaction.followup.send(f"An error occurred while executing command on host '{hostname}'. Please try again later.")
                return

            if not host_data:
                await interaction.followup.send("Host not found. Check your configured hosts.")
                return

            ip, username, password, identification_file, port = host_data

            temp_file_path = f"temp.pem"
            if identification_file:
                with open(temp_file_path, "w") as temp_file:
                    temp_file.write(identification_file)

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
                        password=password,
                        port=port or 22,
                        timeout=10
                    )

                channel = client.get_transport().open_session()
                channel.get_pty()
                channel.invoke_shell()
                
                channel.send(f"{command}\n")
                
                output_lines = deque(maxlen=50)
                complete_output = []
                view = CommandControls(channel, complete_output)
                
                initial_embed = discord.Embed(
                    title=f"Executing Command on Host '{hostname}'",
                    color=discord.Color.blue(),
                    description=f"**Command:**\n```{command}```\n**Live Output:**\n```Initializing...```"
                )
                message = await interaction.followup.send(embed=initial_embed, view=view)
                
                asyncio.create_task(self.read_output(
                    channel, output_lines, complete_output, message, command, hostname, view
                ))

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}")
                if 'client' in locals():
                    client.close()
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

    @execute.autocomplete("hostname")
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
    await bot.add_cog(ExecuteCommand(bot))