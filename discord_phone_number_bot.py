"""
This script runs a Discord bot that monitors multiple websites for new temporary phone numbers 
and sends alerts to a specified Discord channel when new numbers are found.

Websites monitored:
- https://receive-smss.com/
- https://quackr.io/
- https://temp-number.com/

Prerequisites:
- Python 3.8 or higher
- Libraries: requests, beautifulsoup4, discord.py, python-dotenv

Install them using:
pip install requests beautifulsoup4 discord.py python-dotenv
"""

import requests
from bs4 import BeautifulSoup
import json
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import time
import random

# Load environment variables from .env file
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')  # Get the bot token
DISCORD_CHANNEL_ID = int(os.getenv('CHANNEL_ID'))  # Get the channel ID as an integer

# Configuration
# Configuration
WEBSITES = [
    {
        "url": "https://receive-smss.com/",
        "name": "Receive-SMSS",
        "selector": lambda soup: soup.find_all('a', href=lambda x: x and '/sms/' in x)
    },
    {
        "url": "https://sms24.me/en/numbers",
        "name": "SMS24",
        "selector": lambda soup: soup.find_all('a', class_=lambda x: x and 'number-item' in (x or ''))
    },
    {
        "url": "https://freephonenum.com/",
        "name": "FreePhoneNum",
        "selector": lambda soup: soup.find_all('a', class_=lambda x: x and 'number-link' in (x or ''))
    },
    {
        "url": "https://receivesms.co/",
        "name": "ReceiveSMS",
        "selector": lambda soup: soup.find_all('a', href=lambda x: x and '/sms/' in (x or ''))
    }
]


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
            try:
                data = json.load(f)
                print(f"Loaded data type: {type(data)}")
                
                # Check if the loaded data is a list (old format) or dict (new format)
                if isinstance(data, list):
                    # Convert old format to new format
                    print("Converting old numbers format to new format...")
                    return {website["name"]: [] for website in WEBSITES}
                else:
                    # Already in the new format
                    return data
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")
                return {website["name"]: [] for website in WEBSITES}
    except FileNotFoundError:
        print(f"File {JSON_FILE} not found, creating new structure")
        return {website["name"]: [] for website in WEBSITES}

# Function to save the current phone numbers to the JSON file
def save_numbers(numbers):
    with open(JSON_FILE, 'w') as f:
        json.dump(numbers, f, indent=2)  # Save as JSON with pretty formatting

# Function to scrape phone numbers from a website
def scrape_numbers(website):
    try:
        # Add headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        # Send a request to the website with headers
        print(f"Requesting {website['url']}...")
        response = requests.get(website["url"], headers=headers, timeout=15)
        response.raise_for_status()  # Raise an error if the request fails
        
        # Debug: Save HTML to file for inspection
        with open(f"{website['name'].lower()}_debug.html", "w", encoding="utf-8") as f:
            f.write(response.text)
            
        soup = BeautifulSoup(response.text, 'html.parser')  # Parse the HTML
        
        # Use the website-specific selector to find phone number elements
        number_elements = website["selector"](soup)
        numbers = [elem.text.strip() for elem in number_elements if elem.text.strip()]
        
        # Filter out non-numeric content (keeping only strings with at least some digits)
        numbers = [num for num in numbers if any(char.isdigit() for char in num)]
        
        print(f"Found {len(numbers)} numbers on {website['name']}")
        return numbers
    except requests.RequestException as e:
        print(f"Error scraping {website['url']}: {e}")  # Print error if scraping fails
        return []  # Return empty list on error

# Event that runs when the bot is ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')  # Confirm the bot is online
    check_numbers.start()  # Start the periodic task to check for new numbers

# Function to send a message, splitting it if necessary to stay under Discord's character limit
async def send_chunked_message(channel, message_parts, prefix=""):
    chunk = [prefix] if prefix else []
    current_length = len(prefix)
    
    for part in message_parts:
        # +1 for the newline character
        if current_length + len(part) + 1 > 1900:  # Leave some buffer
            await channel.send("\n".join(chunk))
            chunk = [part]
            current_length = len(part)
        else:
            chunk.append(part)
            current_length += len(part) + 1
    
    # Send any remaining parts
    if chunk:
        await channel.send("\n".join(chunk))

# Periodic task to check for new phone numbers
@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def check_numbers():
    channel = bot.get_channel(DISCORD_CHANNEL_ID)  # Get the Discord channel
    if not channel:
        print("Channel not found")  # Print error if channel is invalid
        return
    
    # Load previous numbers
    previous_numbers = load_previous_numbers()
    current_numbers = {}
    
    # Process each website with a delay between requests
    for website in WEBSITES:
        site_name = website["name"]
        print(f"Checking {site_name}...")
        
        # Get current numbers for this site
        site_numbers = scrape_numbers(website)
        current_numbers[site_name] = site_numbers
        
        # Find new numbers (in current but not in previous)
        prev_site_numbers = set(previous_numbers.get(site_name, []))
        new_site_numbers = [num for num in site_numbers if num not in prev_site_numbers]
        
        if new_site_numbers:
            # Send alert for this site
            header = f"📱 New phone numbers found on {site_name}:"
            await channel.send(header)
            
            # Send the numbers in chunks
            await send_chunked_message(channel, new_site_numbers)
            
            print(f"Sent alert for {len(new_site_numbers)} new numbers from {site_name}")
        
        # Add a random delay between requests to avoid being blocked
        if website != WEBSITES[-1]:  # Don't delay after the last website
            delay = random.uniform(3, 7)
            print(f"Waiting {delay:.1f} seconds before next request...")
            time.sleep(delay)
    
    # Save the current numbers for the next check
    save_numbers(current_numbers)

# Run the bot with the Discord token
bot.run(DISCORD_TOKEN)
