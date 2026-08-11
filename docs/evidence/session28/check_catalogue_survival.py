import re, sys
s = open(sys.argv[1], encoding="utf-8", errors="replace").read()
titles = re.findall(r"""["']?(?:title|name)["']?\s*:\s*['"]([^'"]{3,60})['"]""", s)
plumbing = [t for t in ("AI-guided consult", "Member aftercare", "Follow-up visit",
                        "Everyday essential", "Guest favorite") if t in s]
print(f"  imports in mock.ts : {len(re.findall(r'^import ', s, re.M))}")
print(f"  distinct titles    : {len(set(titles))}")
print(f"  sample             : {sorted(set(titles))[:6]}")
print(f"  plumbing残 markers  : {plumbing or 'none'}")
