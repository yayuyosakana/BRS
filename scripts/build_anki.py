#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
レビューテスト_ChXX_*.md → Anki .apkg ビルダー

各 md の「## 問題N（ChX QY）タイトル」ブロックを 1 枚のカードに変換する。
  表面 = BRS英文問題 + 選択肢
  裏面 = 正答 + 和文解説（表・太字つき）
章ごとにサブデッキ「行動科学BRS::ChXX テーマ」へ振り分け、1 つの .apkg にまとめる。

- Markdown→HTML 変換で表・太字をAnki上でも綺麗に表示
- GUID は (章, 問題番号) で固定 → 再ビルドして再インポートすると重複せず上書き更新
"""
import re
import glob
import os
import markdown
import genanki

ROOT = "/Users/yu/Downloads/行動科学"
OUT = os.path.join(ROOT, "行動科学BRS_全章391問.apkg")

# 章番号(2桁文字列) → デッキ表示テーマ（Ch17 は旧名 グループ20 を心理療法に正規化）
THEME = {
    "01": "生涯発達1",        "02": "学童期〜青年期",   "03": "成人期〜老年・死",
    "04": "遺伝と脳",          "05": "症状評価",          "06": "心理的防衛",
    "07": "行動の成り立ち",    "08": "研究手法",          "12": "うつ病",
    "13": "不安症",            "14": "認知症・解離・身体症状", "15": "小児精神・摂食・人格",
    "17": "心理療法",          "18": "家族文化社会",      "19": "性",
    "20": "攻撃と虐待",        "21": "医師患者関係",      "22": "心身医学",
    "23": "医師患者関係・倫理", "24": "法と医療",
}

MODEL_ID = 1607480001          # 固定値（変更厳禁：変えると既存カードと別モデル扱いになる）
DECK_BASE = 1607480100         # デッキIDは DECK_BASE + 章番号

CSS = """
.card { font-family: -apple-system, "Hiragino Sans", "Hiragino Kaku Gothic ProN", sans-serif;
        font-size: 18px; line-height: 1.6; color: #1d1d1f; background: #ffffff;
        text-align: left; max-width: 720px; margin: 0 auto; padding: 4px 10px; }
.qref { color: #8a8a8e; font-size: 13px; margin-bottom: 6px; }
.ans  { color: #b30000; font-weight: 700; }
hr#answer { border: none; border-top: 2px solid #d0d0d5; margin: 14px 0; }
table { border-collapse: collapse; margin: 8px 0; font-size: 15px; }
th, td { border: 1px solid #c4c4c8; padding: 3px 8px; text-align: left; vertical-align: top; }
th { background: #f2f2f4; }
strong { color: #0b3d91; }
ul, ol { margin: 4px 0 4px 1.1em; padding-left: 0.8em; }
li { margin: 2px 0; }
"""

MODEL = genanki.Model(
    MODEL_ID,
    "行動科学BRS レビューテスト",
    fields=[{"name": "Front"}, {"name": "Back"}, {"name": "Ref"}],
    templates=[{
        "name": "Q→A",
        "qfmt": '<div class="qref">{{Ref}}</div>{{Front}}',
        "afmt": '{{FrontSide}}<hr id=answer>{{Back}}',
    }],
    css=CSS,
)

_md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", "nl2br"])


def to_html(text: str) -> str:
    _md.reset()
    return _md.convert(text.strip())


HEADING = re.compile(r"^##\s*問題\s*(\d+)\s*（\s*(.*?)\s*）\s*(.*?)\s*$", re.M)
SEIKAI = re.compile(r"\*\*【正答】\*\*")
TANTOU = re.compile(r"\*\*【担当グループ】\*\*.*?$", re.M)
FILENAME = re.compile(r"レビューテスト_Ch(\d{2})_")


def parse_file(path):
    """1 md ファイル → [(N, qref, title, front_md, back_md), ...]"""
    m = FILENAME.search(os.path.basename(path))
    ch = m.group(1)
    text = open(path, encoding="utf-8").read()
    hs = list(HEADING.finditer(text))
    out = []
    for i, h in enumerate(hs):
        start = h.end()
        end = hs[i + 1].start() if i + 1 < len(hs) else len(text)
        block = text[start:end]
        N, qref, title = h.group(1), h.group(2), h.group(3)

        sm = SEIKAI.search(block)
        if not sm:                       # 正答マーカーが無い＝想定外。スキップして報告
            out.append((N, qref, title, None, None))
            continue
        front_md = block[:sm.start()].strip()
        back_md = block[sm.start():].strip()
        back_md = TANTOU.sub("", back_md).strip()    # 担当グループのフッターを除去
        back_md = back_md.strip("-").strip()         # 末尾の区切り --- を除去
        out.append((N, qref, title, front_md, back_md))
    return ch, out


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "*", "レビューテスト_*.md")))
    decks = []
    total, skipped = 0, []
    for path in files:
        ch, items = parse_file(path)
        theme = THEME.get(ch, "")
        deck = genanki.Deck(DECK_BASE + int(ch), f"行動科学BRS::Ch{ch} {theme}")
        for N, qref, title, front_md, back_md in items:
            if front_md is None:
                skipped.append(f"Ch{ch} 問題{N}（{qref}）: 正答マーカー無し")
                continue
            ref = f"問題{N} ・ {qref}"
            back_caption = f'<div class="qref">📖 {title}</div>' if title else ""
            note = genanki.Note(
                model=MODEL,
                fields=[to_html(front_md), back_caption + to_html(back_md), ref],
                guid=genanki.guid_for(f"koudou-kagaku::Ch{ch}::Q{N}"),
                tags=[f"Ch{ch}", "行動科学BRS"],
            )
            deck.add_note(note)
            total += 1
        decks.append(deck)
        print(f"  Ch{ch} {theme}: {len([i for i in items if i[3] is not None])}問")

    genanki.Package(decks).write_to_file(OUT)
    print(f"\n✅ {total}問 / {len(decks)}デッキ → {OUT}")
    if skipped:
        print("\n⚠️ スキップ:")
        for s in skipped:
            print("   ", s)


if __name__ == "__main__":
    main()
