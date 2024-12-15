# Termicord

[![Development Status](https://img.shields.io/badge/status-alpha-orange)](https://github.com/AbiruEkanayaka/Termicord)
[![Python](https://img.shields.io/badge/python-3.6%2B-blue)](https://www.python.org/)
[![Discord.py](https://img.shields.io/badge/discord.py-latest-blue)](https://discordpy.readthedocs.io/)

Termicord is an open-source Discord bot that enables remote server management via SSH for Debian-based systems. Control and monitor your servers directly through Discord with an intuitive command interface.

## ⚠️ Important Notes

- **Alpha Status**: This project is in active development and may contain bugs
- **Compatibility**: Currently tested only on Debian and Ubuntu systems
- **Security**: Use in production environments at your own risk. As the time of stating, there have been no security risks discovered.
- **Contributions**: Testing on other Debian-based distributions is welcome

## 🚀 Quick Start

### Prerequisites

- Python 3.6 or higher
- pip package manager
- Discord bot token
- SSH access to target servers
- PostgreSQL database

### Installation

1. Clone the repository:
```bash
git clone https://github.com/AbiruEkanayaka/Termicord.git
cd Termicord
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure the bot:
```bash
cp example.config.py config.py
# Edit config.py with your Discord token and database settings
```

4. Initialize the database (Note: Only run this step once in a new PostgreSQL database):
```bash
python db_setup.py
```

5. Launch the bot:
```bash
python app.py
```

## 🎮 Features

### Host Management Commands

| Command | Description |
|---------|-------------|
| `/add-host` | Register a new server |
| `/remove-host` | Delete a server |
| `/list-hosts` | Display registered servers |
| `/edit-host` | Update server details |

### System Control Commands

| Command | Description |
|---------|-------------|
| `/execute` | Run shell commands |
| `/kill` | Terminate processes |
| `/reboot` | Restart server |

### Interactive Terminal

| Command | Description |
|---------|-------------|
| `/live-terminal start` | Begin interactive session |
| `/live-terminal stop` | End interactive session |
| `/live-terminal restart` | Restart inactive session |
| `/live-terminal list` | List active sessions |
| `^C` | Interrupt current process |

### Monitoring Commands

| Command | Description |
|---------|-------------|
| `/ip public` | Display public IP |
| `/ip private` | Display private IP |
| `/ports` | List open ports |
| `/processes` | View process list |
| `/status` | Show system metrics |
| `/users` | List active users |

## 🛠️ Roadmap

- [ ] Add network usage sorting to `/processes`
- [ ] Add better SSH connection handling
- [ ] Implement consistent terminal control using dtach
- [ ] Add support for more Linux distributions
- [ ] Implement session logging
- [ ] Add automated backup functionality
- [ ] Enhance security features

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests, report bugs, or suggest features.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔒 Security

Please use this bot responsibly. Consider these security implications:
- Use strong SSH keys and passwords
- Regularly update both the bot and managed servers
- Monitor and audit command usage

## 📞 Support

- Create an [Issue](https://github.com/AbiruEkanayaka/Termicord/issues) for bug reports
- Submit feature requests through [Discussions](https://github.com/AbiruEkanayaka/Termicord/discussions)
