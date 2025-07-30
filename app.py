from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# Global main key
main_key = "NARAYAN"

# ThreadPool for concurrent image fetching
executor = ThreadPoolExecutor(max_workers=10)

# Fetch player info
def fetch_player_info(uid, region):
    player_info_url = f'https://informacoes-completa-teste.vercel.app/info?uid={uid}&region={region}'
    response = requests.get(player_info_url)
    return response.json() if response.status_code == 200 else None

# Fetch and optionally resize an image
def fetch_and_process_image(image_url, size=None):
    try:
        response = requests.get(image_url)
        if response.status_code == 200:
            image = Image.open(BytesIO(response.content))
            if size:
                image = image.resize(size)
            return image
        else:
            print(f"Failed to fetch image from {image_url}. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error processing image from {image_url}: {e}")
        return None

# Generate outfit image
@app.route('/outfit-image', methods=['GET'])
def outfit_image():
    uid = request.args.get('uid')
    region = request.args.get('region')
    key = request.args.get('key')

    # Validate required parameters and key
    if not uid or not region:
        return jsonify({'error': 'Missing uid or region'}), 400
    if key != main_key:
        return jsonify({'error': 'Invalid or missing API key'}), 403

    player_data = fetch_player_info(uid, region)
    if player_data is None:
        return jsonify({'error': 'Failed to fetch player info'}), 500

    # Get equipped items from profileInfo
    outfit_ids = player_data.get("profileInfo", {}).get("equippedItems", [])
    print(f"Outfit IDs: {outfit_ids}")  # Debug
    
    # Get avatar ID
    avatar_id = player_data.get("profileInfo", {}).get("avatarId", 406)
    print(f"Avatar ID: {avatar_id}")  # Debug
    
    # Get pet ID
    pet_info = player_data.get("petInfo", {})
    pet_id = pet_info.get("id")
    print(f"Pet ID: {pet_id}")  # Debug
    
    # Get weapon ID - using the first weapon skin show
    weapon_id = None
    if "playerData" in player_data and "weaponSkinShows" in player_data["playerData"]:
        weapon_id = player_data["playerData"]["weaponSkinShows"][0] if player_data["playerData"]["weaponSkinShows"] else None
    print(f"Weapon ID: {weapon_id}")  # Debug

    # Required item types and fallback IDs
    required_starts = ["211", "214", "211", "203", "204", "205", "203"]
    fallback_ids = ["211000000", "214000000", "208000000", "203000000", "204000000", "205000000", "212000000"]

    used_ids = set()
    outfit_images = []

    def fetch_outfit_image(idx, code):
        matched = None
        for oid in outfit_ids:
            str_oid = str(oid)
            if str_oid.startswith(code) and oid not in used_ids:
                matched = oid
                used_ids.add(oid)
                break
        if matched is None:
            matched = fallback_ids[idx]
        image_url = f'https://freefireinfo.vercel.app/icon?id={matched}'
        print(f"Fetching outfit item: {image_url}")  # Debug
        return fetch_and_process_image(image_url, size=(150, 150))

    # Fetch all outfit items concurrently
    for idx, code in enumerate(required_starts):
        outfit_images.append(executor.submit(fetch_outfit_image, idx, code))

    # Load background image
    bg_url = 'https://iili.io/F3cIKpp.jpg'
    background_image = fetch_and_process_image(bg_url)
    if not background_image:
        return jsonify({'error': 'Failed to fetch background image'}), 500

    # Positions for each outfit item
    positions = [
        {'x': 512, 'y': 119, 'width': 120, 'height': 120},  # Item 1
        {'x': 100, 'y': 100, 'width': 120, 'height': 120},  # Item 2
        {'x': 590, 'y': 255, 'width': 120, 'height': 120},  # Item 3
        {'x': 500, 'y': 537, 'width': 100, 'height': 100},  # Item 4
        {'x': 27, 'y': 405, 'width': 120, 'height': 120},   # Item 5
        {'x': 115, 'y': 530, 'width': 120, 'height': 120},  # Item 6
        {'x': 30, 'y': 235, 'width': 120, 'height': 120}     # Item 7
    ]

    # Paste all outfit items onto background
    for idx, future in enumerate(outfit_images):
        outfit_image = future.result()
        if outfit_image:
            pos = positions[idx]
            resized = outfit_image.resize((pos['width'], pos['height']))
            background_image.paste(resized, (pos['x'], pos['y']), resized.convert("RGBA"))

    # Add character avatar
    avatar_url = f'https://characteriroxmar.vercel.app/chars?id={avatar_id}'
    print(f"Fetching avatar image: {avatar_url}")  # Debug
    avatar_image = fetch_and_process_image(avatar_url, size=(500, 600))
    if avatar_image:
        center_x = (background_image.width - avatar_image.width) // 2
        center_y = 109
        background_image.paste(avatar_image, (center_x, center_y), avatar_image.convert("RGBA"))
    else:
        print("Failed to fetch avatar image")  # Debug
    
    # Add weapon if available
    if weapon_id:
        weapon_url = f'https://system.ffgarena.cloud/api/iconsff?image={weapon_id}.png'
        print(f"Fetching weapon image: {weapon_url}")  # Debug
        weapon_image = fetch_and_process_image(weapon_url, size=(250, 128))
        
        if weapon_image:
            print("Successfully fetched weapon image")  # Debug
            weapon_x = 460
            weapon_y = 397
            
            if weapon_image.mode != 'RGBA':
                weapon_image = weapon_image.convert('RGBA')
            
            background_image.paste(weapon_image, (weapon_x, weapon_y), weapon_image)
        else:
            print("Failed to fetch weapon image")  # Debug

    # Add pet if available
    if pet_id:
        pet_url = f'https://freefireinfo.vercel.app/icon?id={pet_id}'
        print(f"Fetching pet image: {pet_url}")  # Debug
        pet_image = fetch_and_process_image(pet_url, size=(120, 120))
        
        if pet_image:
            print("Successfully fetched pet image")  # Debug
            pet_x = 600
            pet_y = 500
            background_image.paste(pet_image, (pet_x, pet_y), pet_image.convert("RGBA"))

    # Convert to bytes and send as response
    img_io = BytesIO()
    background_image.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png')

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
