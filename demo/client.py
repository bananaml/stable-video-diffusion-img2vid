# an example client implementation

# pip3 install banana-dev
import banana_dev as client

import base64

# Create a reference to your project on Banana
svd = client.Client(
    api_key="YOUR_API_KEY",
    url="http://localhost:8000", # YOUR_PROJECT_URL
)

# ---------------------------
# Generate the default rocket video
# result, meta = svd.call("/", {})

# video_bytes = base64.b64decode(result.get("mp4_bytes"))
# with open("rocket_out.mp4", 'wb') as f:
#     f.write(video_bytes)

# ---------------------------
# Generate from a local image
# with open("banana.jpg", "rb") as image_file:
#     encoded_string = base64.b64encode(image_file.read())

# inputs = {"image_bytes": encoded_string.decode('utf-8')}

# result, meta = svd.call("/", inputs)

# video_bytes = base64.b64decode(result.get("mp4_bytes"))
# with open("banana_out.mp4", 'wb') as f:
#     f.write(video_bytes)

# ---------------------------
# Generate from a public image url

inputs = {"image_url": "https://m.media-amazon.com/images/I/61ESjh183rL._AC_SL1500_.jpg"}

result, meta = svd.call("/", inputs)

video_bytes = base64.b64decode(result.get("mp4_bytes"))
with open("banana_cage_out.mp4", 'wb') as f:
    f.write(video_bytes)