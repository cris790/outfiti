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
    player_info_url = f'https://informacoes-completa-teste.vercel.app/player-info?region={region}&uid={uid}'
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

    outfit_ids = player_data.get("AccountProfileInfo", {}).get("EquippedOutfit", [])
    equipped_skills = player_data.get("AccountProfileInfo", {}).get("EquippedSkills", [])
    pet_info = player_data.get("petInfo", {})
    pet_id = pet_info.get("id")
    
    # Get first equipped weapon
    equipped_weapons = player_data.get("AccountInfo", {}).get("EquippedWeapon", [])
    weapon_id = equipped_weapons[0] if equipped_weapons else None
    print(f"Weapon ID: {weapon_id}")  # Debug print

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
        return fetch_and_process_image(image_url, size=(150, 150))

    for idx, code in enumerate(required_starts):
        outfit_images.append(executor.submit(fetch_outfit_image, idx, code))

    bg_url = 'https://iili.io/F3cIKpp.jpg'
    background_image = fetch_and_process_image(bg_url)

    if not background_image:
        return jsonify({'error': 'Failed to fetch background image'}), 500

    positions = [
        {'x': 512, 'y': 119, 'width': 120, 'height': 120},
        {'x': 100, 'y': 100, 'width': 120, 'height': 120},
        {'x': 590, 'y': 255, 'width': 120, 'height': 120},
        {'x': 500, 'y': 537, 'width': 100, 'height': 100},
        {'x': 27, 'y': 405, 'width': 120, 'height': 120},
        {'x': 115, 'y': 530, 'width': 120, 'height': 120},
        {'x': 30, 'y': 235, 'width': 120, 'height': 120}
    ]

    for idx, future in enumerate(outfit_images):
        outfit_image = future.result()
        if outfit_image:
            pos = positions[idx]
            resized = outfit_image.resize((pos['width'], pos['height']))
            background_image.paste(resized, (pos['x'], pos['y']), resized.convert("RGBA"))

    # Set avatar position with fixed Y-coordinate
    background_width, background_height = 720, 720

    avatar_id = None
    for skill_id in equipped_skills:
        if str(skill_id).endswith('06'):
            avatar_id = skill_id
            break
    if avatar_id is None:
        avatar_id = 406

    if avatar_id:
        avatar_url = f'https://characteriroxmar.vercel.app/chars?id={avatar_id}'
        avatar_image = fetch_and_process_image(avatar_url, size=(500, 600))
        if avatar_image:
            center_x = (background_width - avatar_image.width) // 2
            center_y = 109
            background_image.paste(avatar_image, (center_x, center_y), avatar_image.convert("RGBA"))
    
    # Add weapon overlay if weapon_id exists
    if weapon_id:
        weapon_url = f'https://system.ffgarena.cloud/api/iconsff?image={weapon_id}.png'
        print(f"Fetching weapon image from: {weapon_url}")  # Debug print
        weapon_image = fetch_and_process_image(weapon_url, size=(250, 128))
        
        if weapon_image:
            print("Successfully fetched weapon image")  # Debug print
            # Position the weapon image (adjusted position)
            weapon_x = 460
            weapon_y = 397
            
            # Ensure the weapon image has an alpha channel
            if weapon_image.mode != 'RGBA':
                weapon_image = weapon_image.convert('RGBA')
            
            background_image.paste(weapon_image, (weapon_x, weapon_y), weapon_image)
        else:
            print("Failed to fetch or process weapon image")  # Debug print

    img_io = BytesIO()
    background_image.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png')

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
