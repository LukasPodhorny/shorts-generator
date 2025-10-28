# pip install requests

import requests
import os

url = "https://api.lemonfox.ai/v1/images/generations"
headers = {
    "Authorization": os.getenv("LEMONFOX_API_KEY"),
    "Content-Type": "application/json",
}
data = {
    "prompt": "A realistic, high-quality scene of President Joe Biden standing in front of a classroom whiteboard, passionately explaining the process of photosynthesis. The whiteboard is filled with colorful diagrams of plants, sunlight, water, and carbon dioxide arrows turning into oxygen and glucose. Biden is gesturing with his hand while speaking, wearing a dark suit and a friendly expression. Bright classroom lighting, cinematic composition, depth of field, ultra-realistic details, 8K, sharp focus, natural skin tones, professional photojournalism style."
}

response = requests.post(url, headers=headers, json=data)
print(response.json())
