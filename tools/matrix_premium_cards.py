from __future__ import annotations

import hashlib
import io
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
BG = (10, 12, 16)
PANEL = (20, 23, 30)
GOLD = (238, 190, 72)
TEXT = (244, 244, 244)
MUTED = (174, 179, 188)
GREEN = (60, 210, 120)
RED = (235, 80, 88)

def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()

def fingerprint(signal_key: str) -> str:
    return hashlib.sha256(str(signal_key).encode("utf-8")).hexdigest()[:12].upper()

def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = str(text or "").split()
    lines, line = [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines or [""]

def _base(signal_key: str) -> tuple[Image.Image, ImageDraw.ImageDraw, str]:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im, "RGBA")
    fp = fingerprint(signal_key)
    # edge frame
    d.rounded_rectangle((34, 34, W-34, H-34), radius=34, outline=GOLD+(220,), width=4)
    # tiled anti-crop watermark
    wm = f"MATRIX PICKS PREMIUM • {fp}"
    wm_font = _font(27, True)
    layer = Image.new("RGBA", (W, H), (0,0,0,0))
    ld = ImageDraw.Draw(layer)
    for y in range(-120, H+180, 150):
        for x in range(-220, W+300, 420):
            ld.text((x,y), wm, font=wm_font, fill=(255,255,255,20))
    layer = layer.rotate(-24, resample=Image.Resampling.BICUBIC, expand=False)
    im = Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    # central forensic seal
    d.text((W//2, H//2), f"MATRIX • {fp}", font=_font(42, True), fill=(238,190,72,30), anchor="mm")
    return im, d, fp

def _header(d, label: str, fp: str, accent: tuple[int,int,int]):
    d.text((80,78), "MATRIX", font=_font(66, True), fill=TEXT)
    d.text((80,150), "PICKS PREMIUM", font=_font(34, True), fill=GOLD)
    d.rounded_rectangle((80,220,1000,305), radius=22, fill=accent+(235,))
    d.text((540,262), label, font=_font(36, True), fill=(255,255,255), anchor="mm")
    d.text((996,92), fp, font=_font(20, True), fill=MUTED, anchor="ra")

def _field(d, y: int, title: str, value: str, *, strong=False):
    d.text((96,y), title.upper(), font=_font(23, True), fill=GOLD)
    font=_font(36 if strong else 31, strong)
    lines=_wrap(d,value,font,860)
    yy=y+37
    for line in lines[:3]:
        d.text((96,yy), line, font=font, fill=TEXT)
        yy += 48 if strong else 42
    return yy+16

def render_pick_png(candidate: dict[str, Any], signal_key: str, output: Path) -> dict[str, Any]:
    im,d,fp=_base(signal_key)
    _header(d,"PICK PUBLICADO",fp,GOLD)
    y=350
    y=_field(d,y,"Partido",candidate.get("match") or "",strong=True)
    y=_field(d,y,"Mercado",candidate.get("market") or "")
    y=_field(d,y,"Casa",str(candidate.get("house") or ""))
    odds=float(candidate.get("odds") or 0)
    d.rounded_rectangle((80,y,1000,y+145),radius=26,fill=PANEL+(255,),outline=GOLD+(150,),width=2)
    d.text((115,y+30),"CUOTA",font=_font(24,True),fill=GOLD)
    d.text((115,y+68),f"{odds:.2f}",font=_font(55,True),fill=TEXT)
    stake=((candidate.get("paper_bet") or {}).get("stake_level") if isinstance(candidate.get("paper_bet"),dict) else None)
    if stake:
        d.text((690,y+30),"STAKE",font=_font(24,True),fill=GOLD)
        d.text((690,y+68),str(int(stake)),font=_font(55,True),fill=TEXT)
    y+=190
    kickoff=str(candidate.get("kickoff_display") or candidate.get("kickoff") or "")
    y=_field(d,y,"Hora",kickoff)
    d.text((540,1185),"ANÁLISIS DEPORTIVO • SIN GARANTÍA DE RESULTADO",font=_font(22,True),fill=MUTED,anchor="mm")
    d.text((540,1230),f"ID VERIFICABLE {fp}",font=_font(21,True),fill=GOLD,anchor="mm")
    output.parent.mkdir(parents=True,exist_ok=True)
    im.save(output,format="PNG",optimize=True)
    return {"path":str(output),"fingerprint":fp,"width":W,"height":H,"kind":"PICK"}

def render_result_png(candidate: dict[str, Any], settlement: dict[str, Any], signal_key: str, output: Path) -> dict[str, Any]:
    won=bool(settlement.get("won"))
    accent=GREEN if won else RED
    im,d,fp=_base(signal_key)
    _header(d,"✅ GANADA" if won else "❌ PERDIDA",fp,accent)
    y=350
    y=_field(d,y,"Partido",candidate.get("match") or settlement.get("match") or "",strong=True)
    score=f'{settlement.get("home_goals")}-{settlement.get("away_goals")}'
    y=_field(d,y,"Resultado final",score,strong=True)
    y=_field(d,y,"Mercado",candidate.get("market") or settlement.get("market") or "")
    y=_field(d,y,"Cuota",f'{float(settlement.get("odds") or 0):.2f}')
    d.rounded_rectangle((80,950,1000,1090),radius=28,fill=accent+(220,))
    d.text((540,1020),"PICK FINALIZADO",font=_font(42,True),fill=(255,255,255),anchor="mm")
    d.text((540,1185),"RESULTADO REGISTRADO POR MATRIX",font=_font(22,True),fill=MUTED,anchor="mm")
    d.text((540,1230),f"ID VERIFICABLE {fp}",font=_font(21,True),fill=GOLD,anchor="mm")
    output.parent.mkdir(parents=True,exist_ok=True)
    im.save(output,format="PNG",optimize=True)
    return {"path":str(output),"fingerprint":fp,"width":W,"height":H,"kind":"RESULT","won":won}

def png_bytes(path: Path) -> bytes:
    data=path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("INVALID_PREMIUM_CARD_PNG")
    return data
