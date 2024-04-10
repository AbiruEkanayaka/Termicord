# Termicord
Termicord is A Open-Source Discord bot written in Python and discord.py to manage VPS servers and any other servers.

## Note:
* Termicord is still is in alpha phase of development and may contain bugs.

## Getting Started

1. Clone the repository
```bash
git clone https://github.com/AbiruEkanayaka/Termicord.git
```
2. Install requirements
```bash
cd Termicord
pip install -r requirements.txt
```
3. Put the token and db config to example.config.py and rename it to config.py
4. Run db_setup.py for a single time
```bash
python db_setup.py
```
5. Run the bot
```bash
python app.py
```

## Usage:

1. `/add-host` use this command to add a host
2. `/remove-host` use this command to remove a host
3. `/execute` executes a bash command based on your selected host

## TODO:

- fix `/execute` for outputs which takes more than 15 minutes.
- Add more commands (/status, /reboot, /cluster, /help)
