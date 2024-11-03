import discord
from discord.ext import commands
from discord import app_commands

class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="📚 Comprehensive list of bot commands")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        embed = discord.Embed(
            title="🤖 Termicord Help Center",
            description=(
                "Welcome to Termicord - Your Advanced SSH Server Management Bot!\n"
                "🔓 **Open Source Project**: [GitHub Repository](https://github.com/AbiruEkanayaka/Termicord)\n"
                "🎯 **Purpose**: Easily manage Debian-based SSH servers through Discord\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=discord.Color.blue()
        )

        # Host Management Section
        embed.add_field(
            name="🏠 Host Management",
            value=(
                "📌 **/add-host** <hostname> <ip> <username> [password] [id_file] [port]\n→ Add a new host to the bot\n"
                "🗑️ **/remove-host** <hostname>\n→ Remove a host from the bot\n"
                "📋 **/list-hosts**\n→ View all your added hosts\n"
                "✏️ **/edit-host** <hostname> <ip> <username> [password] [id_file] [port]\n→ Modify host information"
            ),
            inline=False
        )

        # Command Execution Section
        embed.add_field(
            name="⚡ Function Execution",
            value=(
                "🔄 **/execute** <command> <hostname>\n→ Run commands on target host\n"
                "⛔ **/kill** <pid> <hostname>\n→ Terminate a process\n"
                "🔄 **/reboot** <hostname>\n→ Restart the host"
            ),
            inline=False
        )

        # Live Terminal Section
        embed.add_field(
            name="💻 Live Terminal",
            value=(
                "▶️ **/live-terminal start** <hostname> <channel>\n→ Launch interactive terminal\n"
                "⏹️ **/live-terminal stop** <channel>\n→ End terminal session\n"
                "🔁 **/live-terminal restart** <channel>\n→ Restart inactive session\n"
                "📊 **/live-terminal list**\n→ View active terminals\n"
                "⚡ **Special Command**: ^C\n→ Interrupt current process"
            ),
            inline=False
        )

        # System Information Section
        embed.add_field(
            name="ℹ️ System Information",
            value=(
                "🌐 **/ip public**\n→ Show public IP address\n"
                "🔒 **/ip private**\n→ Show private IP address\n"
                "🔍 **/ports**\n→ List open TCP/UDP ports\n"
                "📊 **/processes** <hostname> [sort]\n→ View sorted process list\n"
                "📈 **/status**\n→ Show host resource status\n"
                "👥 **/users**\n→ List connected users"
            ),
            inline=False
        )

        # Footer with warning
        embed.set_footer(text="⚠️ This is an open-source project with no warranties. Use at your own discretion.")
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCommand(bot))