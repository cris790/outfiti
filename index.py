from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image, ImageFilter, ImageOps
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import re

app = Flask(__name__)

main_key = "narayan"
executor = ThreadPoolExecutor(max_workers=10)

# Configuration for image positioning and sizing
IMAGE_CONFIG = {
    "BACKGROUND": {"url": "https://iili.io/3LlJ82s.jpg"},
    "OUTFIT_PARTS": [
        {"x": 110, "y": 90, "w": 120, "h": 120},
        {"x": 485, "y": 85, "w": 120, "h": 120},
        {"x": 570, "y": 215, "w": 120, "h": 120},
        {"x": 32, "y": 220, "w": 120, "h": 120},
        {"x": 27, "y": 395, "w": 120, "h": 120},
        {"x": 115, "y": 520, "w": 120, "h": 120},
        {"x": 492, "y": 537, "w": 100, "h": 100}
    ],
    "AVATAR": {"x": 315, "y": 300, "w": 90, "h": 90},
    "CHARACTER": {"x": 95, "y": 80, "w": 525, "h": 625},
    "WEAPONS": [
        {"x": 465, "y": 395, "w": 250, "h": 125}
    ]
}

def fetch_player_info(uid, region):
    url = f'https://grandmixture-id-info.vercel.app/player-info?region={region}&uid={uid}'
    response = requests.get(url)
    return response.json() if response.status_code == 200 else None

def fetch_and_process_image(image_url, size=None, remove_bg=False, alpha_threshold=200):
    try:
        response = requests.get(image_url)
        if response.status_code == 200:
            image = Image.open(BytesIO(response.content)).convert("RGBA")
            
            if remove_bg:
                # Create a mask for background removal
                datas = image.getdata()
                new_data = []
                for item in datas:
                    r, g, b, a = item
                    # Only remove pure white/very light backgrounds
                    if (r > 240 and g > 240 and b > 240) or a == 0:
                        new_data.append((255, 255, 255, 0))
                    else:
                        # Preserve all other colors including character colors
                        new_data.append(item)
                image.putdata(new_data)
            
            if size:
                image = image.resize(size, Image.LANCZOS)
            return image
    except Exception as e:
        print(f"Error processing image: {e}")
    return None

@app.route('/outfit-image', methods=['GET'])
def outfit_image():
    uid = request.args.get('uid')
    region = request.args.get('region')
    key = request.args.get('key')
    char_width = request.args.get('char_width', default=IMAGE_CONFIG["CHARACTER"]["w"], type=int)
    char_height = request.args.get('char_height', default=IMAGE_CONFIG["CHARACTER"]["h"], type=int)
    weapon_size = request.args.get('weapon_size', default=150, type=int)
    remove_bg = request.args.get('remove_bg', default='true').lower() == 'true'

    if not uid or not region:
        return jsonify({'error': 'Missing uid or region'}), 400
    if key != main_key:
        return jsonify({'error': 'Invalid or missing API key'}), 403

    player_data = fetch_player_info(uid, region)
    if not player_data:
        return jsonify({'error': 'Failed to fetch player info'}), 500

    outfit_ids = player_data.get("AccountProfileInfo", {}).get("EquippedOutfit", [])
    skills = player_data.get("AccountProfileInfo", {}).get("EquippedSkills", [])
    pet_id = player_data.get("petInfo", {}).get("id")
    avatar_id = player_data.get("AccountInfo", {}).get("AccountAvatarId")
    weapons = player_data.get("AccountInfo", {}).get("EquippedWeapon", [])

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

    background_image = fetch_and_process_image(IMAGE_CONFIG["BACKGROUND"]["url"])
    if not background_image:
        return jsonify({'error': 'Failed to fetch background image'}), 500

    for idx, future in enumerate(outfit_images):
        outfit_image = future.result()
        if outfit_image:
            pos = IMAGE_CONFIG["OUTFIT_PARTS"][idx]
            resized = outfit_image.resize((pos['w'], pos['h']), Image.LANCZOS)
            background_image.paste(resized, (pos['x'], pos['y']), resized)

    if avatar_id:
        avatar_url = f'https://as-image.onrender.com/image?id={avatar_id}'
        avatar_image = fetch_and_process_image(avatar_url, size=(IMAGE_CONFIG["AVATAR"]["w"], IMAGE_CONFIG["AVATAR"]["h"]))
        if avatar_image:
            background_image.paste(avatar_image, (IMAGE_CONFIG["AVATAR"]["x"], IMAGE_CONFIG["AVATAR"]["y"]), avatar_image)

    if skills and isinstance(skills, list) and len(skills) > 0:
        skill_id = skills[1] if len(skills) > 1 else skills[0]
        char_api_url = f'https://character-roan.vercel.app/Character_name/Id={skill_id}'
        try:
            char_response = requests.get(char_api_url)
            if char_response.status_code == 200:
                char_data = char_response.json()
                char_image_url = char_data.get("Png Image")
                if char_image_url:
                    temp_img = fetch_and_process_image(char_image_url)
                    if temp_img:
                        orig_ratio = temp_img.width / temp_img.height
                        config_ratio = IMAGE_CONFIG["CHARACTER"]["w"] / IMAGE_CONFIG["CHARACTER"]["h"]
                        
                        if orig_ratio > config_ratio:
                            char_width = IMAGE_CONFIG["CHARACTER"]["w"]
                            char_height = int(char_width / orig_ratio)
                        else:
                            char_height = IMAGE_CONFIG["CHARACTER"]["h"]
                            char_width = int(char_height * orig_ratio)
                        
                        char_x = IMAGE_CONFIG["CHARACTER"]["x"] + (IMAGE_CONFIG["CHARACTER"]["w"] - char_width) // 2
                        char_y = IMAGE_CONFIG["CHARACTER"]["y"] + (IMAGE_CONFIG["CHARACTER"]["h"] - char_height) // 2
                        
                        character_image = fetch_and_process_image(
                            char_image_url, 
                            size=(char_width, char_height),
                            remove_bg=remove_bg
                        )
                        if character_image:
                            background_image.paste(character_image, (char_x, char_y), character_image)
        except Exception as e:
            print(f"Error fetching character info: {e}")

    if weapons and isinstance(weapons, list):
        for idx, weapon_id in enumerate(weapons[:3]):
            if idx >= len(IMAGE_CONFIG["WEAPONS"]):
                break
                
            weapon_url = f'https://freefireinfo.vercel.app/icon?id={weapon_id}'
            weapon_image = fetch_and_process_image(
                weapon_url, 
                size=(weapon_size, weapon_size), 
                remove_bg=True
            )
            if weapon_image:
                pos = IMAGE_CONFIG["WEAPONS"][idx]
                resized = weapon_image.resize((pos['w'], pos['h']), Image.LANCZOS)
                background_image.paste(resized, (pos['x'], pos['y']), resized)

    img_io = BytesIO()
    background_image.save(img_io, 'PNG', optimize=True, quality=95)
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png')

@app.route('/character-info', methods=['GET'])
def character_info():
    uid = request.args.get('uid')
    region = request.args.get('region')
    key = request.args.get('key')

    if not uid or not region:
        return jsonify({'error': 'Missing uid or region'}), 400
    if key != main_key:
        return jsonify({'error': 'Invalid or missing API key'}), 403

    player_data = fetch_player_info(uid, region)
    if not player_data:
        return jsonify({'error': 'Failed to fetch player info'}), 500

    skills = player_data.get("AccountProfileInfo", {}).get("EquippedSkills", [])

    skill_id = None
    if isinstance(skills, list) and len(skills) > 1:
        skill_id = skills[1]
    elif isinstance(skills, list) and len(skills) == 1:
        skill_id = skills[0]

    if not skill_id:
        return jsonify({'error': 'Skill ID not found'}), 404

    char_api_url = f'https://character-roan.vercel.app/Character_name/Id={skill_id}'

    try:
        char_response = requests.get(char_api_url)
        if char_response.status_code == 200:
            char_data = char_response.json()
            png_url = char_data.get("Png Image")
            if png_url:
                return jsonify({
                    'skill_id': skill_id,
                    'png_url': png_url,
                    'character_name': char_data.get("Character Name"),
                    'character_info': {
                        'description': char_data.get("Description"),
                        'skill_name': char_data.get("Skill Name"),
                        'skill_description': char_data.get("Skill Description")
                    },
                    'character_config': IMAGE_CONFIG["CHARACTER"]
                })
            else:
                return jsonify({'error': 'Png Image not found in character response'}), 404
        else:
            return jsonify({'error': 'Failed to get character info'}), 500
    except Exception as e:
        return jsonify({'error': f'Exception: {str(e)}'}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
