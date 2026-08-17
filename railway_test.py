import requests
from bs4 import BeautifulSoup

URL = "https://www.shahrekhabar.com/"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
}

try:
    response = requests.get(
        URL,
        headers=headers,
        timeout=30
    )

    print("HTTP:", response.status_code)
    print("SIZE:", len(response.content))

    soup = BeautifulSoup(response.text, "html.parser")

    print("\nعنوان صفحه:")
    print(soup.title.get_text(strip=True) if soup.title else "پیدا نشد")

    print("\nچند لینک اول:")
    count = 0

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "/news/" in href:
            text = a.get_text(" ", strip=True)

            if text:
                print(text[:100])
                print(href)
                print("-" * 40)

                count += 1

            if count >= 5:
                break

except Exception as e:
    print("ERROR:", repr(e))
