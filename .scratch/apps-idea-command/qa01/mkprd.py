import sys, re
sys.path.insert(0, sys.argv[1])
import importlib.util
spec = importlib.util.spec_from_file_location("ta", sys.argv[1] + "/test_apps.py")
src = open(sys.argv[1] + "/test_apps.py", encoding="utf-8").read()
good = re.search(r'^GOOD = """\\\n(.*?)^"""', src, re.S | re.M).group(1)
name, slug, out = sys.argv[2], sys.argv[3], sys.argv[4]
text = (good.replace("APP-003", "APP-006").replace("app-003", "app-006")
        .replace("Delivery order maker", name).replace("delivery-order-maker", slug)
        .replace("2026-10-26", "2026-11-01"))
open(out, "w", encoding="utf-8").write(text)
