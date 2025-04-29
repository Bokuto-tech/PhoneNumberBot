import requests
from bs4 import BeautifulSoup
import json
import discord
from discord.ext import tasks, commands
import asyncio

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration
WEBSITE_URL = "https://receive-smss.com/"  # Replace with actual URL
DISCORD_CHANNEL_ID = YOUR_CHANNEL_ID  # Replace with your Discord channel ID
CHECK_INTERVAL_MINUTES = 15
JSON_FILE = "numbers.json"

# Load previous numbers from JSON file
def load_previous_numbers():
    try:
        with open(JSON_FILE, 'r') as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

# Save current numbers to JSON file
def save_numbers(numbers):
    with open(JSON_FILE, 'w') as f:
        json.dump(list(numbers), f)

# Scrape phone numbers from the website
def scrape_numbers():
    try:
        response = requests.get(WEBSITE_URL, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Adjust this based on the website's HTML structure
        number_elements = soup.find_all('div', class_='number-box')  # Example class
        numbers = {element.text.strip() for element in number_elements if element.text.strip()}
        return numbers
    except Exception as e:
        print(f"Error scraping numbers: {e}")
        return set()

# Discord bot events
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    check_numbers.start()

# Periodic task to check for new numbers
@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def check_numbers():
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print("Channel not found")
        return

    # Load previous numbers and scrape new ones
    previous_numbers = load_previous_numbers()
    current_numbers = scrape_numbers()
    
    # Find new numbers
    new_numbers = current_numbers - previous_numbers
    if new_numbers:
        message = "New temporary phone numbers found:\n" + "\n".join(new_numbers)
        await channel.send(message)
        print(f"Sent alert for {len(new_numbers)} new numbers")
    
    # Save current numbers
    save_numbers(current_numbers)

# Run the bot
bot.run('YOUR_BOT_TOKEN')  # Replace with your bot token