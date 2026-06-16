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
OUT = os.path.join(ROOT, "行動科学BRS_全章419問.apkg")

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


SUBQ = re.compile(r"^\s*\*\*Q\s*(\d+)\s*[:：]")          # 小問の見出し行
CHOICE = re.compile(r"\([A-Z]\)")                          # 選択肢 (A)〜


def expand_qs(qref):
    """（Ch7 Q3, Q4, Q5）/（Ch13 Q1-3）→ [3,4,5] / [1,2,3]"""
    rest = re.sub(r"Ch\s*\d+", "", qref)
    rest = re.sub(r"[QqＱ]", "", rest)
    qs = []
    for a, b, s in re.findall(r"(\d+)\s*-\s*(\d+)|(\d+)", rest):
        if s:
            qs.append(int(s))
        else:
            qs += list(range(int(a), int(b) + 1))
    return qs


def split_merged(front_md, back_md):
    """統合カードを 小問ごと (qn, front_md, back_md) に分解。
    共通選択肢型・小問別選択肢型の両方に対応。失敗時は None。"""
    m = re.search(r"\*\*【正答】\*\*(.*?)(?=\*\*【解説】\*\*|$)", back_md, re.S)
    if not m:
        return None
    ans_text = m.group(1).strip()
    kaisetsu = back_md[m.start():]                          # 【正答】以降だが…
    kaisetsu = back_md[m.end():].lstrip()                   # 【解説】から
    # 小問ごとの正答を抽出： "Q3: (B)…　Q4: (E)…"
    ans_map = {}
    for mm in re.finditer(r"Q\s*(\d+)\s*[:：]\s*(.*?)(?=(?:Q\s*\d+\s*[:：])|$)",
                          ans_text, re.S):
        ans_map[int(mm.group(1))] = mm.group(2).strip().strip("　").strip()

    lines = front_md.split("\n")
    sub_idx = [i for i, l in enumerate(lines) if SUBQ.match(l)]
    if not sub_idx or not ans_map:
        return None
    scenario = "\n".join(lines[:sub_idx[0]]).strip()
    order, segs = [], {}
    for j, si in enumerate(sub_idx):
        qn = int(SUBQ.match(lines[si]).group(1))
        end = sub_idx[j + 1] if j + 1 < len(sub_idx) else len(lines)
        order.append(qn)
        segs[qn] = lines[si:end]

    def has_choice(seg):
        return any(CHOICE.search(l) for l in seg)

    per_q = any(has_choice(segs[q]) for q in order[:-1])    # 小問間に選択肢→個別型
    shared = ""
    if not per_q:                                           # 共通選択肢型
        last = order[-1]
        shared = "\n".join(segs[last][1:]).strip()          # 末尾の共通選択肢
        segs[last] = [segs[last][0]]                         # 最後の小問は設問行のみに

    out = []
    for qn in order:
        qline = segs[qn][0].strip()
        if per_q:
            front = scenario + "\n\n" + "\n".join(segs[qn]).strip()
        else:
            front = scenario + "\n\n" + qline + "\n\n" + shared
        ans = ans_map.get(qn, "")
        back = f"**【正答】** {ans}\n\n" + kaisetsu
        out.append((qn, front.strip(), back.strip()))
    return out


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "*", "レビューテスト_*.md")))
    decks = {}              # 章番号(int) → genanki.Deck （qref記載の章に振り分ける）
    seen = set()            # GUID重複の最終防波堤
    total, split_n, board_n, skipped = 0, 0, 0, []

    def get_deck(chap):
        if chap not in decks:
            ch2 = f"{chap:02d}"
            decks[chap] = genanki.Deck(
                DECK_BASE + chap, f"行動科学BRS::Ch{ch2} {THEME.get(ch2, '')}")
        return decks[chap]

    def add(chap, guid_key, front_md, back_md, title, ref, tags):
        guid = genanki.guid_for(f"koudou-kagaku::Ch{chap}::{guid_key}")
        if guid in seen:
            skipped.append(f"GUID重複でスキップ: Ch{chap} {guid_key}")
            return False
        seen.add(guid)
        cap = f'<div class="qref">📖 {title}</div>' if title else ""
        get_deck(chap).add_note(genanki.Note(
            model=MODEL,
            fields=[to_html(front_md), cap + to_html(back_md), ref],
            guid=guid, tags=tags,
        ))
        return True

    for path in files:
        file_ch, items = parse_file(path)
        for N, qref, title, front_md, back_md in items:
            if front_md is None:
                skipped.append(f"Ch{file_ch} 問題{N}（{qref}）: 正答マーカー無し")
                continue
            m = re.search(r"Ch\s*(\d+)", qref)
            chap = int(m.group(1)) if m else int(file_ch)    # qref記載の章を優先
            qs = expand_qs(qref)

            if not qs:                                       # Q番号なし＝Typical Board Question等
                if add(chap, f"Board{N}", front_md, back_md, title,
                       f"Ch{chap} ボード問題", [f"Ch{chap:02d}", "行動科学BRS", "board_question"]):
                    total += 1; board_n += 1
            elif len(qs) == 1:                               # 単問：そのまま
                q = qs[0]
                if add(chap, f"Q{q:02d}", front_md, back_md, title,
                       f"Ch{chap} Q{q}", [f"Ch{chap:02d}", "行動科学BRS"]):
                    total += 1
            else:                                            # 統合：小問ごとに分割
                parts = split_merged(front_md, back_md)
                if not parts:
                    skipped.append(f"Ch{file_ch} 問題{N}（{qref}）: 分割失敗→統合のまま")
                    if add(chap, f"Q{qs[0]:02d}", front_md, back_md, title,
                           f"Ch{chap} {qref}", [f"Ch{chap:02d}", "行動科学BRS"]):
                        total += 1
                    continue
                for qn, fmd, bmd in parts:
                    if add(chap, f"Q{qn:02d}", fmd, bmd, title,
                           f"Ch{chap} Q{qn}", [f"Ch{chap:02d}", "行動科学BRS", "matched_set"]):
                        total += 1; split_n += 1

    pkg_decks = [decks[c] for c in sorted(decks)]
    genanki.Package(pkg_decks).write_to_file(OUT)
    print(f"✅ {total}カード（分割生成{split_n} / ボード問題{board_n}）/ {len(pkg_decks)}デッキ → {OUT}")
    if skipped:
        print("\n⚠️ スキップ/要確認:")
        for s in skipped:
            print("   ", s)


if __name__ == "__main__":
    main()
