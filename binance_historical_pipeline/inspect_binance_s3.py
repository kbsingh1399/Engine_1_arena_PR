"""
================================================================================
INSPECT BINANCE VISION S3 BUCKET INDEX
================================================================================
Queries S3 XML listing on https://s3-ap-northeast-1.amazonaws.com/data.binance.vision
to discover all available folders under data/futures/um/daily/
================================================================================
"""

import urllib.request
import xml.etree.ElementTree as ET

def list_bucket(prefix):
    url = f"https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix={prefix}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            xml_content = r.read()
            root = ET.fromstring(xml_content)
            # Find CommonPrefixes
            prefixes = []
            for p in root.findall("{http://s3.amazonaws.com/doc/2006-03-01/}CommonPrefixes"):
                pref = p.find("{http://s3.amazonaws.com/doc/2006-03-01/}Prefix").text
                prefixes.append(pref)
            return prefixes
    except Exception as e:
        print("Error listing bucket:", e)
        return []

def main():
    print("Folders under data/futures/um/daily/:")
    prefixes = list_bucket("data/futures/um/daily/")
    for p in prefixes:
        print("  -", p)

    print("\nFolders under data/futures/um/monthly/:")
    prefixes_m = list_bucket("data/futures/um/monthly/")
    for p in prefixes_m:
        print("  -", p)

if __name__ == "__main__":
    main()
