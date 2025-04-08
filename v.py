import requests

def extract_cookie_string_from_netscape(file_path):
    cookie_string = ""
    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            if not line.strip().startswith("#") and line.strip() != "":
                parts = line.strip().split("\t")
                if len(parts) == 7:
                    domain, flag, path, secure, expiry, name, value = parts
                    cookie_string += f"{name}={value}; "
    return cookie_string.strip()

# Path to your exported YouTube cookie file
cookie_file_path = "yt_cookies.txt"  # change if your file has a different name

# Extract cookie string
cookie_string = extract_cookie_string_from_netscape(cookie_file_path)

# Set headers including cookie string and user-agent
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Cookie": cookie_string
}

# Send a request to test the cookies
url = "https://www.youtube.com"  # or use any valid YouTube endpoint you want
response = requests.get(url, headers=headers)

# Output status
print("Status Code:", response.status_code)
if response.ok:
    print("Successfully authenticated with YouTube using cookies!")
else:
    print("Failed to authenticate. Check if cookies are still valid.")
