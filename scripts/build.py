"""
프로필 README에 쓰이는 SVG를 생성합니다.

  pip install fonttools brotli
  python scripts/build.py

- 프로젝트는 포트폴리오 사이트의 projects.json 에서 가져옵니다(PROJECTS_URL).
  README.md 의 <!-- projects:start --> ~ <!-- projects:end --> 사이도 이 스크립트가 다시 씁니다.
- 프로필 문구·스택은 아래 DATA 영역에서 고칩니다.
- GitHub Actions(.github/workflows/update-profile.yml)가 매일 이 스크립트를 실행하고,
  바뀐 내용이 있을 때만 커밋합니다.
- 라이트/다크 두 벌을 assets/ 에 만듭니다. README는 <picture>로 테마에 맞는 쪽을 보여 줍니다.
- 글꼴(IBM Plex Mono, Pretendard · 둘 다 OFL)은 scripts/.fonts 에 처음 한 번 내려받고,
  SVG마다 실제로 쓴 글자만 잘라 woff2로 넣습니다. 그래서 보는 사람 PC에 글꼴이 없어도 똑같이 보입니다.
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONT_DIR = Path(__file__).resolve().parent / ".fonts"

# ─────────────────────────────────────────────────────────────── DATA ──

PROFILE = {
    "handle": "CLOCKTICK0127",
    "name": "최준혁",
    "tagline": "새로운 것을 배우며 적응합니다.",
    "focus": "web game  ·  real-time  ·  data pipeline",
    "now": "지금은 삼성 청년 SW 아카데미(SSAFY) 15기",
    # 시계 바늘이 가리키는 시각. 0127 → 01:27
    "clock": (1, 27),
}

# 프로젝트는 포트폴리오 사이트의 projects.json 을 그대로 씁니다.
# 사이트에서 프로젝트를 추가·수정하면 다음 빌드(매일 자동 실행)에서 프로필에도 반영됩니다.
PROJECTS_URL = os.environ.get("PROJECTS_URL", "https://clocktick0127.github.io/projects.json")
MAX_PROJECTS = 4  # 프로필에 보여 줄 최대 개수 (projects.json 앞에서부터)

# 카드를 눌렀을 때 갈 곳. 앞에 있는 것부터 쓰고, 비공개 GitHub 저장소는 건너뜁니다.
LINK_PRIORITY = ["repo", "youtube", "demo", "gitlab", "docs"]

STACK = [
    ("Language", ["Java", "Python", "TypeScript", "JavaScript"]),
    ("Frontend", ["React", "Vue", "React Query"]),
    ("Backend", ["Spring Boot", "Django", "Node.js"]),
    ("Data · Infra", ["MySQL", "Redis", "Kafka", "MQTT", "Docker"]),
]

SECTIONS = [
    ("projects", "01", "Projects", "최근 작업부터 · 담당 역할과 결과"),
    ("side", "02", "Side", "혼자 만들어 본 도구들"),
    ("stack", "03", "Stack", "써 본 기술"),
]

# ──────────────────────────────────────────────────────────── THEMES ──
# 배경은 투명. GitHub 페이지 배경 위에 그대로 얹힙니다.

THEMES = {
    "light": {
        "page": "#ffffff",
        "ink": "#1f2328",
        "muted": "#59636e",
        "faint": "#8c959f",
        "line": "#d1d9e0",
        "accent": "#e5532d",
    },
    "dark": {
        "page": "#0d1117",
        "ink": "#f0f6fc",
        "muted": "#9198a1",
        "faint": "#656c76",
        "line": "#3d444d",
        "accent": "#ff7b5c",
    },
}

W = 840

# ───────────────────────────────────────────────────────────── FONTS ──

FONT_SOURCES = {
    "mono": ("IBMPlexMono-Regular.ttf", "https://github.com/google/fonts/raw/main/ofl/ibmplexmono/IBMPlexMono-Regular.ttf"),
    "mono-md": ("IBMPlexMono-Medium.ttf", "https://github.com/google/fonts/raw/main/ofl/ibmplexmono/IBMPlexMono-Medium.ttf"),
    "sans": ("Pretendard-Regular.otf", "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-Regular.otf"),
    "sans-sb": ("Pretendard-SemiBold.otf", "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-SemiBold.otf"),
    "sans-b": ("Pretendard-Bold.otf", "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-Bold.otf"),
}
FALLBACK = {
    "mono": "'IBM Plex Mono',SFMono-Regular,Consolas,Menlo,monospace",
    "sans": "Pretendard,-apple-system,'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif",
}


class Font:
    def __init__(self, key: str):
        fname, url = FONT_SOURCES[key]
        self.key = key
        self.path = FONT_DIR / fname
        if not self.path.exists():
            FONT_DIR.mkdir(parents=True, exist_ok=True)
            print(f"  downloading {fname}")
            urllib.request.urlretrieve(url, self.path)
        self.tt = TTFont(self.path)
        self.cmap = self.tt.getBestCmap()
        self.hmtx = self.tt["hmtx"]
        self.upm = self.tt["head"].unitsPerEm
        self.family = f"ct-{key}"
        self.fallback = FALLBACK["mono" if key.startswith("mono") else "sans"]

    def width(self, text: str, size: float, ls: float = 0) -> float:
        total = 0.0
        for ch in text:
            gid = self.cmap.get(ord(ch))
            total += (self.hmtx[gid][0] / self.upm * size) if gid else size * 0.6
        return total + ls * max(len(text) - 1, 0)

    def woff2_b64(self, chars: set[str]) -> str:
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.hinting = False
        opts.desubroutinize = True
        opts.name_IDs = [1, 2]
        opts.notdef_outline = True
        opts.drop_tables += ["meta"]
        # recalcTimestamp=False: 저장 시각이 글꼴에 박히면 매번 결과가 달라져 매일 커밋이 생깁니다.
        font = TTFont(self.path, recalcTimestamp=False)
        sub = subset.Subsetter(opts)
        sub.populate(text="".join(sorted(chars)))
        sub.subset(font)
        buf = io.BytesIO()
        font.flavor = "woff2"
        font.save(buf)
        return base64.b64encode(buf.getvalue()).decode()


FONTS: dict[str, Font] = {}


def F(key: str) -> Font:
    if key not in FONTS:
        FONTS[key] = Font(key)
    return FONTS[key]


# ──────────────────────────────────────────────────────────── CANVAS ──

class Svg:
    def __init__(self, width: int, title: str, theme: str):
        self.w = width
        self.title = title
        self.c = THEMES[theme]
        self.body: list[str] = []
        self.used: dict[str, set[str]] = {}

    def add(self, s: str):
        self.body.append(s)

    def text(self, x, y, s, face="sans", size=16, color="ink", anchor="start", ls=0.0, extra=""):
        self.used.setdefault(face, set()).update(s)
        f = F(face)
        fill = self.c.get(color, color)
        ls_attr = f' letter-spacing="{ls}"' if ls else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{f.family},{escape(f.fallback, {chr(39): "&apos;"})}" '
            f'font-size="{size}" fill="{fill}" text-anchor="{anchor}"{ls_attr}{extra}>{escape(s)}</text>'
        )

    def render(self, height: float) -> str:
        faces = []
        for key, chars in sorted(self.used.items()):
            faces.append(
                f"@font-face{{font-family:'{F(key).family}';"
                f"src:url(data:font/woff2;base64,{F(key).woff2_b64(chars | {' '})}) format('woff2');}}"
            )
        h = math.ceil(height)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{h}" '
            f'viewBox="0 0 {self.w} {h}" role="img" aria-label="{escape(self.title)}">\n'
            f"<title>{escape(self.title)}</title>\n"
            f"<style>{''.join(faces)}</style>\n" + "\n".join(self.body) + "\n</svg>\n"
        )


def wrap(text: str, face: str, size: float, max_w: float) -> list[str]:
    f = F(face)
    lines, cur = [], ""
    for word in text.split(" "):
        trial = f"{cur} {word}".strip()
        if f.width(trial, size) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def polar(cx, cy, r, deg):
    a = math.radians(deg - 90)
    return cx + r * math.cos(a), cy + r * math.sin(a)


# ─────────────────────────────────────────────────────────── HEADER ──

def header(theme: str) -> str:
    p = PROFILE
    s = Svg(W, f"{p['name']} · {p['handle']} — {p['tagline']}", theme)
    c = s.c
    H = 300

    # 왼쪽: 이름과 소개
    x = 4
    s.text(x, 74, p["handle"], "mono-md", 13, "muted", ls=2.2)
    s.text(x, 146, p["name"], "sans-b", 68, "ink", ls=-1.5)
    s.text(x, 192, p["tagline"], "sans", 21, "ink")
    s.text(x, 222, p["focus"], "mono", 14, "muted")

    # 지금 상태 (깜빡이는 점)
    s.add(
        f'<circle cx="{x + 5}" cy="{262 - 5}" r="4.5" fill="{c["accent"]}">'
        f'<animate attributeName="opacity" values="1;.25;1" dur="2.4s" repeatCount="indefinite"/></circle>'
    )
    s.text(x + 20, 262, p["now"], "sans", 15, "muted")

    # 오른쪽: 시계
    cx, cy, R = 708, 150, 112
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{c["line"]}" stroke-width="1"/>')
    for i in range(60):
        major = i % 5 == 0
        r_in = R - (17 if major else 10)
        x1, y1 = polar(cx, cy, R - 6, i * 6)
        x2, y2 = polar(cx, cy, r_in, i * 6)
        s.add(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{c["ink"] if major else c["faint"]}" stroke-width="{2.2 if major else 1}" stroke-linecap="round"/>'
        )

    hh, mm = p["clock"]
    s.text(cx, cy - 40, f"{hh:02d}:{mm:02d}", "mono", 12, "faint", anchor="middle", ls=1.5)

    def hand(deg, length, width, color, tail=0):
        return (
            f'<line x1="{cx}" y1="{cy + tail}" x2="{cx}" y2="{cy - length}" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round" transform="rotate({deg:.2f} {cx} {cy})"/>'
        )

    s.add(hand((hh % 12 + mm / 60) * 30, R * 0.48, 5.5, c["ink"]))
    s.add(hand(mm * 6, R * 0.74, 3.5, c["ink"]))

    # 초침: 1초에 한 칸씩 뚝뚝 움직입니다
    steps = ";".join(f"{i * 6} {cx} {cy}" for i in range(60))
    s.add(
        f'<g><line x1="{cx}" y1="{cy + 22}" x2="{cx}" y2="{cy - R * 0.86:.1f}" stroke="{c["accent"]}" '
        f'stroke-width="1.6" stroke-linecap="round"/>'
        f'<circle cx="{cx}" cy="{cy}" r="4.5" fill="{c["accent"]}"/>'
        f'<animateTransform attributeName="transform" type="rotate" values="{steps}" '
        f'dur="60s" calcMode="discrete" repeatCount="indefinite"/></g>'
    )
    s.add(f'<circle cx="{cx}" cy="{cy}" r="1.6" fill="{c["page"]}"/>')
    return s.render(H)


# ────────────────────────────────────────────────────── SECTION HEAD ──

def section_head(num: str, title: str, desc: str, theme: str) -> str:
    s = Svg(W, f"{num} {title} — {desc}", theme)
    c = s.c
    base = 80
    s.text(0, 48, num, "mono-md", 14, "accent", ls=1)
    tx = 34
    s.text(tx, 50, title, "sans-b", 26, "ink", ls=-0.3)
    dx = tx + F("sans-b").width(title, 26, -0.3) + 14
    s.text(dx, 49, desc, "sans", 15, "muted")
    # 눈금자: 10px마다 짧은 눈금, 50px마다 긴 눈금
    s.add(f'<line x1="0" y1="{base}" x2="{W}" y2="{base}" stroke="{c["line"]}" stroke-width="1"/>')
    ticks = []
    for i, xx in enumerate(range(0, W + 1, 10)):
        h = 8 if i % 5 == 0 else 4
        ticks.append(f"M{xx},{base}v-{h}")
    s.add(f'<path d="{"".join(ticks)}" stroke="{c["line"]}" stroke-width="1"/>')
    s.add(f'<path d="M0,{base}v-8" stroke="{c["accent"]}" stroke-width="2"/>')
    return s.render(base + 6)


# ────────────────────────────────────────────────────────── PROJECT ──

def project_row(i: int, p: dict, theme: str) -> str:
    s = Svg(W, f"{p['title']} — {p['subtitle']}" if p["subtitle"] else p["title"], theme)
    c = s.c
    gutter, rail, x0 = 168, 192, 220
    max_w = W - x0 - 4

    # 왼쪽: 번호 · 기간 · 분야
    s.text(gutter, 46, f"{i + 1:02d}", "mono-md", 14, "accent", anchor="end", ls=1)
    meta_y = 70
    for value, face, size, color in (
        (p["period"], "mono", 12.5, "muted"),
        (p["category"], "mono", 12, "faint"),
        (p["team"], "sans", 13, "faint"),
    ):
        if value:
            s.text(gutter, meta_y, value, face, size, color, anchor="end")
            meta_y += 20

    # 오른쪽: 내용
    y = 48
    s.text(x0, y, p["title"], "sans-b", 30, "ink", ls=-0.4)
    y += 32
    for line in wrap(p["subtitle"], "sans", 16.5, max_w) if p["subtitle"] else []:
        s.text(x0, y, line, "sans", 16.5, "muted")
        y += 25

    y += 12
    label_w = 74
    for label, value in (("ROLE", p["role"]), ("RESULT", p["outcome"])):
        if not value:
            continue
        lines = wrap(value, "sans", 15, max_w - label_w)
        s.text(x0, y - 1, label, "mono-md", 11, "faint", ls=1.4)
        for line in lines:
            s.text(x0 + label_w, y, line, "sans", 15, "ink")
            y += 23
        y += 3

    y += 12
    cx = x0
    for tag in p["tags"]:
        tw = F("mono").width(tag, 12.5) + 22
        s.add(
            f'<rect x="{cx + 0.5}" y="{y - 17.5}" width="{tw:.1f}" height="25" rx="12.5" '
            f'fill="none" stroke="{c["line"]}"/>'
        )
        s.text(cx + tw / 2, y, tag, "mono", 12.5, "muted", anchor="middle")
        cx += tw + 7
    H = max(y + 34, meta_y + 20)

    # 타임라인: 점선 레일 + 마커 (마커 뒤는 페이지 배경색으로 가림)
    s.body.insert(
        0,
        f'<line x1="{rail}" y1="0" x2="{rail}" y2="{H}" stroke="{c["line"]}" '
        f'stroke-width="1.2" stroke-dasharray="2 5"/>',
    )
    s.add(
        f'<circle cx="{rail}" cy="40" r="6" fill="{c["page"]}" '
        f'stroke="{c["accent"] if i == 0 else c["ink"]}" stroke-width="2"/>'
    )
    return s.render(H)


# ──────────────────────────────────────────────────────────── STACK ──

def stack(theme: str) -> str:
    s = Svg(W, "Stack — " + " / ".join(f"{g}: {', '.join(items)}" for g, items in STACK), theme)
    c = s.c
    col_w = W / len(STACK)
    rows = max(len(items) for _, items in STACK)
    for k, (group, items) in enumerate(STACK):
        x = k * col_w
        s.text(x, 24, group.upper(), "mono-md", 11.5, "faint", ls=1.6)
        s.add(f'<line x1="{x}" y1="40" x2="{x + col_w - 24}" y2="40" stroke="{c["line"]}"/>')
        s.add(f'<line x1="{x}" y1="40" x2="{x + 18}" y2="40" stroke="{c["ink"]}" stroke-width="2"/>')
        for j, item in enumerate(items):
            s.text(x, 72 + j * 30, item, "sans-sb", 16.5, "ink")
    return s.render(72 + (rows - 1) * 30 + 22)


# ───────────────────────────────────────────────────────────── MAIN ──

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "clocktick-profile-build"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()


def is_public(url: str) -> bool:
    """github.com 저장소 링크면 공개 여부를 확인합니다. 비공개면 로그인 없이 404가 납니다."""
    m = re.match(r"https://github\.com/([^/]+)/([^/#?]+)", url)
    if not m:
        return True
    try:
        fetch(f"https://github.com/{m[1]}/{m[2]}")
        return True
    except urllib.error.HTTPError as e:
        return e.code != 404


def youtube_url(v: str) -> str:
    return v if v.startswith("http") else f"https://www.youtube.com/watch?v={v}"


def load_projects() -> list[dict]:
    raw = json.loads(fetch(PROJECTS_URL))
    if not isinstance(raw, list) or not raw:
        raise SystemExit(f"projects.json 이 비어 있거나 형식이 다릅니다: {PROJECTS_URL}")

    projects = []
    for item in raw[:MAX_PROJECTS]:
        links = dict(item.get("links") or {})
        yt = links.get("youtube") or item.get("youtube") or item.get("youtubeId")
        if yt:
            links["youtube"] = youtube_url(yt)
        href = next(
            (links[k] for k in LINK_PRIORITY if links.get(k) and "your-id" not in links[k] and is_public(links[k])),
            "",
        )
        team = (item.get("team") or "").strip()
        if team and "팀" not in team:
            team += " 팀"
        projects.append({
            "title": item["title"],
            "subtitle": item.get("subtitle", ""),
            "category": item.get("category", ""),
            "period": item.get("period", ""),
            "team": team,
            "role": item.get("role") or item.get("focus", ""),
            "outcome": item.get("outcome", ""),
            "tags": item.get("tags") or [],
            "href": href,
        })
    return projects


def write(path: Path, text: str):
    # 어느 OS에서 돌려도 결과가 같도록 줄바꿈을 LF로 고정합니다.
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"  {path.relative_to(ROOT).as_posix():40s} {len(text.encode()) / 1024:6.1f} KB")


def picture(base: str, alt: str) -> str:
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="assets/{base}-dark.svg">\n'
        f'  <img src="assets/{base}-light.svg" width="100%" alt="{escape(alt, {chr(34): "&quot;"})}">\n'
        "</picture>"
    )


def projects_block(projects: list[dict]) -> str:
    rows = []
    for i, p in enumerate(projects):
        facts = ", ".join(x for x in (p["period"], p["team"]) if x)
        alt = f"{p['title']}" + (f" ({facts})" if facts else "") + (f" — {p['subtitle']}" if p["subtitle"] else "")
        if p["role"]:
            alt += f". 담당: {p['role']}"
        if p["outcome"]:
            alt += f". 결과: {p['outcome']}"
        pic = picture(f"project-{i + 1:02d}", alt)
        rows.append(f'<a href="{escape(p["href"])}">{pic}</a>' if p["href"] else pic)
    # <div>로 감싸야 GitHub가 <a><picture>를 쪼개지 않고 라이트/다크 전환도 제대로 됩니다.
    return "<div>\n" + "\n".join(rows) + "\n</div>"


def update_readme(projects: list[dict]):
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    start, end = "<!-- projects:start -->", "<!-- projects:end -->"
    if start not in text or end not in text:
        raise SystemExit("README.md 에 <!-- projects:start --> / <!-- projects:end --> 표시가 없습니다.")
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    write(path, f"{head}{start}\n{projects_block(projects)}\n{end}{tail}")


def main():
    ASSETS.mkdir(exist_ok=True)
    projects = load_projects()
    print(f"  projects.json → {len(projects)}개: {', '.join(p['title'] for p in projects)}")

    made = set()
    for theme in THEMES:
        files = {f"header-{theme}.svg": header(theme), f"stack-{theme}.svg": stack(theme)}
        for slug, num, title, desc in SECTIONS:
            files[f"section-{slug}-{theme}.svg"] = section_head(num, title, desc, theme)
        for i, p in enumerate(projects):
            files[f"project-{i + 1:02d}-{theme}.svg"] = project_row(i, p, theme)
        for name, svg in files.items():
            write(ASSETS / name, svg)
            made.add(name)

    # 프로젝트가 줄었거나 이름 규칙이 바뀌어 더는 쓰지 않는 SVG는 지웁니다.
    for old in ASSETS.glob("*.svg"):
        if old.name not in made:
            old.unlink()
            print(f"  removed {old.name}")

    update_readme(projects)


if __name__ == "__main__":
    main()
