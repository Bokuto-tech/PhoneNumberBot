"""
This script runs a Discord bot that monitors the website https://receive-smss.com/ for new temporary phone numbers and sends alerts to a specified Discord channel when new numbers are found.

Prerequisites:
- Python 3.8 or higher
- Libraries: requests, beautifulsoup4, discord.py, python-dotenv

Install them using:
pip install requests beautifulsoup4 discord.py python-dotenv

Setup:
1. Create a Discord bot:
   - Go to https://discord.com/developers/applications
   - Create a new application
   - Go to Bot tab and add a bot
   - Copy the token

2. Invite the bot to your server:
   - Go to OAuth2 > URL Generator
   - Select bot scope
   - Select permissions: Send Messages, Read Messages/View Channels
   - Copy the generated URL and open it to invite the bot to your server

3. Get the channel ID:
   - In Discord, enable Developer Mode (User Settings > Advanced > Developer Mode)
   - Right-click the channel you want to send messages to and select Copy ID

4. Create a .env file in the same directory as this script with:
   DISCORD_TOKEN=your_bot_token_here
   CHANNEL_ID=your_channel_id_here

5. Run the script:
   python bot.py

Note:
- You may need to adjust the scraping logic in the scrape_numbers function based on the website's HTML structure. Inspect the website (right-click > Inspect) to find the correct HTML elements containing the phone numbers.
- If the website uses JavaScript to load numbers, consider using Playwright (pip install playwright) instead of requests.
- To monitor multiple websites, define a list of URLs and loop through them in check_numbers.
- Check the website's terms of service to ensure scraping is permitted.
"""

import requests
from bs4 import BeautifulSoup
import json
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')  # Get the bot token
DISCORD_CHANNEL_ID = int(os.getenv('CHANNEL_ID'))  # Get the channel ID as an integer

# Configuration
WEBSITE_URL = "https://receive-smss.com/"  # Website to monitor for phone numbers
JSON_FILE = "numbers.json"  # File to store previously seen numbers
CHECK_INTERVAL_MINUTES = 15  # How often to check for new numbers

# Set up Discord bot with necessary permissions (intents)
intents = discord.Intents.default()
intents.message_content = True  # Allow the bot to send messages
bot = commands.Bot(command_prefix='!', intents=intents)  # Create the bot with a command prefix

# Function to load previously seen phone numbers from the JSON file
def load_previous_numbers():
    try:
        with open(JSON_FILE, 'r') as f:
            return set(json.load(f))  # Convert list from JSON to a set
    except FileNotFoundError:
        return set()  # Return empty set if file doesn't exist

# Function to save the current phone numbers to the JSON file
def save_numbers(numbers):
    with open(JSON_FILE, 'w') as f:
        json.dump(list(numbers), f)  # Convert set to list and save to JSON

# Function to scrape phone numbers from the website
def scrape_numbers():
    try:
        # Send a request to the website
        response = requests.get(WEBSITE_URL, timeout=10)
        response.raise_for_status()  # Raise an error if the request fails
        soup = BeautifulSoup(response.text, 'html.parser')  # Parse the HTML
        # Find all <a> tags that link to SMS pages (assumed to contain phone numbers)
        # Adjust this selector based on the website's actual HTML structure
        number_links = soup.find_all('div', href=lambda x: x and '/sms/' in x)
        numbers = {a.text.strip() for a in number_links}  # Extract text and store in a set
        return numbers
    except requests.RequestException as e:
        print(f"Error scraping {WEBSITE_URL}: {e}")  # Print error if scraping fails
        return set()  # Return empty set on error
    # Alternative approach: Use the phonenumbers library to extract numbers from text
    # Install with: pip install phonenumbers
    # Example:
    # import phonenumbers
    # text = soup.get_text()
    # numbers = {phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
    #            for match in phonenumbers.PhoneNumberMatcher(text, None)}

# Event that runs when the bot is ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')  # Confirm the bot is online
    check_numbers.start()  # Start the periodic task to check for new numbers

# Periodic task to check for new phone numbers every 15 minutes
@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def check_numbers():
    channel = bot.get_channel(DISCORD_CHANNEL_ID)  # Get the Discord channel
    if not channel:
        print("Channel not found")  # Print error if channel is invalid
        return
    # Load previous numbers and scrape new ones
    previous_numbers = load_previous_numbers()
    current_numbers = scrape_numbers()
    # Find new numbers (in current but not in previous)
    new_numbers = current_numbers - previous_numbers
    if new_numbers:
        # Create a message with the new numbers
        message = "New temporary phone numbers found:\n" + "\n".join(new_numbers)
        await channel.send(message)  # Send the message to the channel
        print(f"Sent alert for {len(new_numbers)} new numbers")
    # Save the current numbers for the next check
    save_numbers(current_numbers)

# Run the bot with the Discord token
bot.run(DISCORD_TOKEN)