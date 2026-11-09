import requests
url = "https://eoimages.gsfc.nasa.gov/images/imagerecord/57000/57752/land_shallow_topo_2048.jpg"
r = requests.get(url, timeout=30)
print(r.status_code)
open("earth_texture.jpg", "wb").write(r.content)
print("Saved!")
